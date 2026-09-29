defmodule WebsiteWeb.SeoController do
  @moduledoc """
  Serves crawler-facing files that need absolute URLs (robots.txt, sitemap.xml).
  """
  use WebsiteWeb, :controller

  def robots(conn, _params) do
    body = """
    User-agent: *
    Allow: /

    Sitemap: #{url(~p"/sitemap.xml")}
    """

    conn
    |> put_resp_content_type("text/plain")
    |> send_resp(200, body)
  end

  def sitemap(conn, _params) do
    body = """
    <?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url>
        <loc>#{url(~p"/")}</loc>
        <changefreq>weekly</changefreq>
        <priority>1.0</priority>
      </url>
    </urlset>
    """

    conn
    |> put_resp_content_type("application/xml")
    |> send_resp(200, body)
  end
end
