defmodule WebsiteWeb.SeoControllerTest do
  use WebsiteWeb.ConnCase

  test "robots.txt allows crawling and points to the sitemap", %{conn: conn} do
    body = get(conn, ~p"/robots.txt") |> response(200)

    assert body =~ "User-agent: *"
    assert body =~ "Allow: /"
    assert body =~ "/sitemap.xml"
  end

  test "sitemap.xml lists the site root", %{conn: conn} do
    body = get(conn, ~p"/sitemap.xml") |> response(200)

    assert body =~ "<urlset"
    assert body =~ "<loc>"
  end
end
