defmodule WebsiteWeb.HomeLiveTest do
  use WebsiteWeb.ConnCase

  import Phoenix.LiveViewTest

  test "renders the landing page", %{conn: conn} do
    {:ok, _view, html} = live(conn, ~p"/")

    assert html =~ "without trusting it"
    assert html =~ "What it defends against"
    assert html =~ "Standing on the shoulders of giants"
  end

  test "includes SEO metadata", %{conn: conn} do
    {:ok, _view, html} = live(conn, ~p"/")

    assert html =~ ~s(rel="canonical")
    assert html =~ ~s(property="og:title")
    assert html =~ ~s(name="twitter:card" content="summary_large_image")
    assert html =~ "application/ld+json"
    assert html =~ ~s(property="og:image" content=)
  end
end
