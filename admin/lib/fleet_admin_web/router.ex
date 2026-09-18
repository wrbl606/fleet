defmodule FleetAdminWeb.Router do
  use FleetAdminWeb, :router

  pipeline :browser do
    plug :accepts, ["html"]
    plug :fetch_session
    plug :fetch_live_flash
    plug :put_root_layout, html: {FleetAdminWeb.Layouts, :root}
    plug :protect_from_forgery
    plug :put_secure_browser_headers
    plug FleetAdminWeb.Plugs.AdminAuth
  end

  pipeline :api do
    plug :accepts, ["json"]
    plug FleetAdminWeb.Plugs.ApiAuth
  end

  scope "/api", FleetAdminWeb do
    pipe_through :api

    post "/ingest", IngestController, :create
    get "/metrics", MetricsController, :show
  end

  scope "/", FleetAdminWeb do
    pipe_through :browser

    live "/", RunLive.Index, :index
    live "/runs/:id", RunLive.Show, :show
    live "/trigger", TriggerLive, :index
    live "/gitops", GitOpsLive, :index
  end

  # Enable LiveDashboard and Swoosh mailbox preview in development
  if Application.compile_env(:fleet_admin, :dev_routes) do
    # If you want to use the LiveDashboard in production, you should put
    # it behind authentication and allow only admins to access it.
    # If your application does not have an admins-only section yet,
    # you can use Plug.BasicAuth to set up some basic authentication
    # as long as you are also using SSL (which you should anyway).
    import Phoenix.LiveDashboard.Router

    scope "/dev" do
      pipe_through :browser

      live_dashboard "/dashboard", metrics: FleetAdminWeb.Telemetry
      forward "/mailbox", Plug.Swoosh.MailboxPreview
    end
  end
end
