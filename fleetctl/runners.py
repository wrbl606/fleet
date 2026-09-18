"""Runner backends (P0/P3/P4).

The dispatcher only sees :class:`RunnerBackend`; the platform-specific part is
how a command is executed:

  * :class:`CoiRunnerBackend` - Linux, ``coi run`` (Incus container + active
    defense). Every setup/agent/verify command runs inside the sandbox and the
    exit code is propagated.
  * :class:`NativeRunnerBackend` - macOS/Windows bare-metal, native execution.
    Only reachable for allowlisted repos (enforced in the registry layer).

``NativeRunnerBackend`` is included now so ``[platform]`` routing has a target;
its host hardening is the P4 runbook (docs/security.md).
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Mapping, Optional, Sequence

from .agents import build_agent_command
from .coi_config import parse_duration
from .errors import RunnerError
from .exec_ import Executor
from .models import FleetManifest, RunPlan, StepResult


class RunnerBackend:
    def __init__(self, plan: RunPlan, workspace: str, executor: Executor) -> None:
        self.plan = plan
        self.workspace = str(Path(workspace).resolve())
        self.executor = executor
        self.manifest: FleetManifest = plan.manifest

    # -- steps --------------------------------------------------------------
    def run_setup(self) -> StepResult:
        raise NotImplementedError

    def run_agent(self, prompt: str) -> StepResult:
        raise NotImplementedError

    def run_verify(self) -> StepResult:
        raise NotImplementedError

    def cleanup(self) -> None:
        """Best-effort resource cleanup after a run."""

    # -- helpers ------------------------------------------------------------
    def _timeout(self) -> float:
        return parse_duration(self.manifest.coi.timeout) + 180

    def _file_exists(self, relpath: Optional[str]) -> bool:
        return bool(relpath) and (Path(self.workspace) / ".fleet" / relpath).is_file()

    def _script_rel(self, relpath: str) -> str:
        return f".fleet/{relpath}"

    def _step_argv(self, command: Sequence[str]) -> list[str]:
        raise NotImplementedError


class CoiRunnerBackend(RunnerBackend):
    def __init__(
        self,
        plan: RunPlan,
        workspace: str,
        executor: Executor,
        *,
        coi_config_path: str,
    ) -> None:
        super().__init__(plan, workspace, executor)
        self.coi_config_path = coi_config_path

    def _step_argv(self, command: Sequence[str]) -> list[str]:
        argv = ["coi", "run"]
        profile = self.manifest.coi.profile
        if profile:
            argv += ["--profile", profile]
        argv += ["--workspace", self.workspace, "--", *command]
        return argv

    def _env(self) -> Mapping[str, str]:
        env = {"COI_CONFIG": self.coi_config_path}
        llm_env = self.manifest.agent.llm_env
        if llm_env and llm_env in os.environ:
            env[llm_env] = os.environ[llm_env]
        return env

    def _run(self, name: str, command: Sequence[str]) -> StepResult:
        result = self.executor.run(
            self._step_argv(command),
            cwd=self.workspace,
            env=self._env(),
            timeout=self._timeout(),
        )
        result.name = name
        return result

    def run_setup(self) -> StepResult:
        script = self.manifest.setup.script
        if not self._file_exists(script):
            return StepResult(name="setup", exit_code=0, stdout="(no setup script)")
        return self._run("setup", ["bash", self._script_rel(script)])

    def run_agent(self, prompt: str) -> StepResult:
        return self._run("agent", build_agent_command(self.manifest, prompt))

    def run_verify(self) -> StepResult:
        script = self.manifest.verify.script
        if not self._file_exists(script):
            return StepResult(name="verify", exit_code=0, stdout="(no verify script)")
        return self._run("verify", ["bash", self._script_rel(script)])

    def cleanup(self) -> None:
        if shutil.which("coi") is None:
            return
        self.executor.run(
            ["coi", "clean", "--force"],
            cwd=self.workspace,
            timeout=120,
        )


class NativeRunnerBackend(RunnerBackend):
    def __init__(self, plan: RunPlan, workspace: str, executor: Executor) -> None:
        super().__init__(plan, workspace, executor)
        if not plan.resolution.native:
            raise RunnerError(
                "NativeRunnerBackend instantiated for a linux/COI task; "
                "this is a routing bug (fail closed)"
            )
        if os.name == "nt" and plan.resolution.platform != "windows":
            raise RunnerError("windows runner on a non-windows host")
        if plan.resolution.platform == "windows" and os.name != "nt":
            raise RunnerError("windows runner requires a Windows host")

    def _script_argv(self, script: str) -> list[str]:
        if self.manifest.platform.os == "windows":
            return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script]
        return ["bash", script]

    def _wrap(self, command: Sequence[str]) -> list[str]:
        """Apply the trusted host-side OS sandbox for this native platform."""
        resolution = self.plan.resolution
        opts = resolution.native_options or {}
        if resolution.platform == "macos":
            profile = opts.get("seatbelt_profile")
            if profile:
                if not Path(profile).is_file():
                    raise RunnerError(f"seatbelt profile not found: {profile}")
                return [
                    "sandbox-exec",
                    "-D",
                    f"WORKSPACE={self.workspace}",
                    "-f",
                    str(profile),
                    *command,
                ]
        elif resolution.platform == "windows":
            wrapper = opts.get("windows_wrapper") or []
            if wrapper:
                return [*wrapper, *command]
        return list(command)

    def _step_argv(self, command: Sequence[str]) -> list[str]:
        return list(command)

    def _run(self, name: str, command: Sequence[str]) -> StepResult:
        result = self.executor.run(
            self._wrap(command),
            cwd=self.workspace,
            timeout=self._timeout(),
        )
        result.name = name
        return result

    def run_setup(self) -> StepResult:
        script = self.manifest.setup.script
        if not self._file_exists(script):
            return StepResult(name="setup", exit_code=0, stdout="(no setup script)")
        return self._run("setup", self._script_argv(self._script_rel(script)))

    def run_agent(self, prompt: str) -> StepResult:
        return self._run("agent", build_agent_command(self.manifest, prompt))

    def run_verify(self) -> StepResult:
        script = self.manifest.verify.script
        if not self._file_exists(script):
            return StepResult(name="verify", exit_code=0, stdout="(no verify script)")
        return self._run("verify", self._script_argv(self._script_rel(script)))


def make_backend(
    plan: RunPlan,
    workspace: str,
    executor: Executor,
    *,
    coi_config_path: str,
) -> RunnerBackend:
    if plan.resolution.native:
        return NativeRunnerBackend(plan, workspace, executor)
    return CoiRunnerBackend(plan, workspace, executor, coi_config_path=coi_config_path)
