# To learn more about how to use Nix to configure your environment
# see: https://developers.google.com/idx/guides/customize-idx-env

{ pkgs ? import <nixpkgs> {} }:

{
  # Which nixpkgs channel to use.
  channel = "unstable";

  # Use https://search.nixos.org/packages to find packages
  packages = [
    pkgs.python311
  ];

  # Sets environment variables in the workspace
  env = {
  };
  idx = {
    # Search for the extensions you want on https://open-vsx.org/ and use "publisher.id"
    extensions = [
        "ms-python.python"
    ];

    # Workspace lifecycle hooks
    workspace = {
      onCreate = {
        create-venv = ''
          python3 -m venv .venv
          source .venv/bin/activate
          pip install -r requirements.txt
        '';
      };
      onStart = {
      };
    };
  };
}