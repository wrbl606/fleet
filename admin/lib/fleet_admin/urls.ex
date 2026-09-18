defmodule FleetAdmin.Urls do
  @moduledoc """
  URL normalization helpers.

  A stored/configured URL without a scheme (e.g. `jenkins.internal:8080`) is
  not navigable as an absolute link — browsers may treat it as a custom
  protocol and offer to "open"/download it. Normalizing to an absolute URL
  keeps Jenkins links clickable.
  """

  @doc """
  Trims and ensures an absolute URL has a scheme.

  Returns `nil` for blank input. Values already containing a scheme are
  returned unchanged (so `https://…` and `file://…` are preserved).
  """
  def normalize(nil), do: nil

  def normalize(url) when is_binary(url) do
    url = String.trim(url)

    cond do
      url == "" -> nil
      String.contains?(url, "://") -> url
      true -> "http://" <> url
    end
  end

  def normalize(_other), do: nil

  @doc "Like `normalize/1` but with any trailing slashes removed."
  def normalize_base(url) do
    case normalize(url) do
      nil -> nil
      normalized -> String.trim_trailing(normalized, "/")
    end
  end
end
