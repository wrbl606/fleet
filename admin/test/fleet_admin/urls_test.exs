defmodule FleetAdmin.UrlsTest do
  use ExUnit.Case, async: true

  alias FleetAdmin.Urls

  test "normalize/1 keeps absolute URLs" do
    assert Urls.normalize("https://jenkins.example/job/x/") ==
             "https://jenkins.example/job/x/"

    assert Urls.normalize("http://localhost:8080") == "http://localhost:8080"
  end

  test "normalize/1 adds a scheme to schemeless hosts" do
    assert Urls.normalize("jenkins.internal:8080/job/x/") ==
             "http://jenkins.internal:8080/job/x/"

    assert Urls.normalize("192.168.1.10:8080") == "http://192.168.1.10:8080"
  end

  test "normalize/1 trims and handles blanks" do
    assert Urls.normalize("  http://localhost:8080  ") == "http://localhost:8080"
    assert Urls.normalize("") == nil
    assert Urls.normalize(nil) == nil
  end

  test "normalize_base/1 removes trailing slashes" do
    assert Urls.normalize_base("http://localhost:8080/") == "http://localhost:8080"
    assert Urls.normalize_base("https://jenkins.example///") == "https://jenkins.example"
    assert Urls.normalize_base(nil) == nil
  end
end
