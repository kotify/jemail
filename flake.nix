{
  description = "jemail";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?ref=nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs { inherit system; };
        lib = pkgs.lib;
        app-test = pkgs.writeShellScriptBin "app.test" "pytest $@";
        app-install = pkgs.writeShellScriptBin "app.install" "uv sync && pre-commit install";
        app-lint = pkgs.writeShellScriptBin "app.lint" "pre-commit run -a";
      in
      {
        devShells.default = pkgs.mkShell {
          packages = [
            pkgs.python313
            pkgs.uv
            pkgs.pyright
          ];
          buildInputs = [
            app-test
            app-install
            app-lint
          ];
          shellHook = ''
            export PYTHONUNBUFFERED=1;
            export PYTHONPATH=src;
            export DJANGO_SETTINGS_MODULE=tests.settings;
            export VIRTUAL_ENV="$(pwd)/.venv"
            [[ -d $VIRTUAL_ENV ]] || ${lib.getExe pkgs.uv} -q venv --python ${lib.getExe pkgs.python313} "$VIRTUAL_ENV"
            export PATH="$VIRTUAL_ENV/bin":$PATH
          '';
        };
      }
    );
}
