defmodule WebsiteWeb.Layouts do
  @moduledoc """
  This module holds layouts and related functionality
  used by your application.
  """
  use WebsiteWeb, :html

  # Embed all files in layouts/* within this module.
  # The default root.html.heex file contains the HTML
  # skeleton of your application, namely HTML headers
  # and other static content.
  embed_templates "layouts/*"

  @doc """
  Renders your app layout.

  This function is typically invoked from every template,
  and it often contains your application menu, sidebar,
  or similar.

  ## Examples

      <Layouts.app flash={@flash}>
        <h1>Content</h1>
      </Layouts.app>

  """
  attr :flash, :map, required: true, doc: "the map of flash messages"

  attr :current_scope, :map,
    default: nil,
    doc: "the current [scope](https://phoenix.hexdocs.pm/scopes.html)"

  slot :inner_block, required: true

  def app(assigns) do
    ~H"""
    <div class="min-h-screen bg-base-300 text-base-content selection:bg-primary/30">
      <div class="pointer-events-none fixed inset-0 bg-grid opacity-[0.35]"></div>
      <div class="pointer-events-none fixed left-1/2 top-0 h-[520px] w-[900px] -translate-x-1/2 rounded-full bg-primary/20 blur-[140px]">
      </div>

      <div class="relative">
        <header class="sticky top-0 z-50 border-b border-base-content/5 bg-base-300/70 backdrop-blur-xl">
          <div class="mx-auto flex max-w-7xl items-center justify-between px-6 py-4 lg:px-8">
            <a href="#top" class="group flex items-center gap-3">
              <span class="grid size-9 place-items-center rounded-xl bg-gradient-to-br from-primary to-accent text-primary-content shadow-lg shadow-primary/30">
                <.icon name="hero-command-line" class="size-5" />
              </span>
              <span class="flex flex-col leading-none">
                <span class="font-mono text-sm font-semibold tracking-tight">fleet</span>
                <span class="text-[10px] uppercase tracking-[0.2em] text-base-content/50">
                  remote AI, safely
                </span>
              </span>
            </a>

            <nav class="hidden items-center gap-1 text-sm text-base-content/70 md:flex">
              <a
                href="#security"
                class="rounded-lg px-3 py-2 transition hover:bg-base-content/5 hover:text-base-content"
              >Security</a>
              <a
                href="#stack"
                class="rounded-lg px-3 py-2 transition hover:bg-base-content/5 hover:text-base-content"
              >Stack</a>
              <a
                href="#concepts"
                class="rounded-lg px-3 py-2 transition hover:bg-base-content/5 hover:text-base-content"
              >Concepts</a>
              <a
                href="#start"
                class="rounded-lg px-3 py-2 transition hover:bg-base-content/5 hover:text-base-content"
              >Quickstart</a>
              <a
                href="#docs"
                class="rounded-lg px-3 py-2 transition hover:bg-base-content/5 hover:text-base-content"
              >Docs</a>
            </nav>

            <div class="flex items-center gap-3">
              <.theme_toggle />
              <a
                href="https://github.com"
                class="hidden items-center gap-2 rounded-xl border border-base-content/10 bg-base-content/5 px-4 py-2 text-sm font-medium transition hover:border-base-content/20 hover:bg-base-content/10 sm:flex"
              >
                <.icon name="hero-code-bracket" class="size-4" /> Source
              </a>
            </div>
          </div>
        </header>

        {render_slot(@inner_block)}
      </div>
    </div>

    <.flash_group flash={@flash} />
    """
  end

  @doc """
  Shows the flash group with standard titles and content.

  ## Examples

      <.flash_group flash={@flash} />
  """
  attr :flash, :map, required: true, doc: "the map of flash messages"
  attr :id, :string, default: "flash-group", doc: "the optional id of flash container"

  def flash_group(assigns) do
    ~H"""
    <div id={@id} aria-live="polite">
      <.flash kind={:info} flash={@flash} />
      <.flash kind={:error} flash={@flash} />

      <.flash
        id="client-error"
        kind={:error}
        title="We can't find the internet"
        phx-disconnected={
          show(".phx-client-error #client-error")
          |> JS.remove_attribute("hidden", to: ".phx-client-error #client-error")
        }
        phx-connected={hide("#client-error") |> JS.set_attribute({"hidden", ""})}
        hidden
      >
        Attempting to reconnect
        <.icon name="hero-arrow-path" class="ml-1 size-3 motion-safe:animate-spin" />
      </.flash>

      <.flash
        id="server-error"
        kind={:error}
        title="Something went wrong!"
        phx-disconnected={
          show(".phx-server-error #server-error")
          |> JS.remove_attribute("hidden", to: ".phx-server-error #server-error")
        }
        phx-connected={hide("#server-error") |> JS.set_attribute({"hidden", ""})}
        hidden
      >
        Attempting to reconnect
        <.icon name="hero-arrow-path" class="ml-1 size-3 motion-safe:animate-spin" />
      </.flash>
    </div>
    """
  end

  @doc """
  Provides dark vs light theme toggle based on themes defined in app.css.

  See <head> in root.html.heex which applies the theme before page load.
  """
  def theme_toggle(assigns) do
    ~H"""
    <div class="card relative flex flex-row items-center border-2 border-base-300 bg-base-300 rounded-full">
      <div class="absolute w-1/3 h-full rounded-full border-1 border-base-200 bg-base-100 brightness-200 left-0 [[data-theme=light]_&]:left-1/3 [[data-theme=dark]_&]:left-2/3 [[data-theme-source=system]_&]:!left-0 transition-[left]" />

      <button
        class="flex p-2 cursor-pointer w-1/3"
        phx-click={JS.dispatch("phx:set-theme")}
        data-phx-theme="system"
      >
        <.icon name="hero-computer-desktop-micro" class="size-4 opacity-75 hover:opacity-100" />
      </button>

      <button
        class="flex p-2 cursor-pointer w-1/3"
        phx-click={JS.dispatch("phx:set-theme")}
        data-phx-theme="light"
      >
        <.icon name="hero-sun-micro" class="size-4 opacity-75 hover:opacity-100" />
      </button>

      <button
        class="flex p-2 cursor-pointer w-1/3"
        phx-click={JS.dispatch("phx:set-theme")}
        data-phx-theme="dark"
      >
        <.icon name="hero-moon-micro" class="size-4 opacity-75 hover:opacity-100" />
      </button>
    </div>
    """
  end
end
