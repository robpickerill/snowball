{
  description = "slr-snowball: citation snowballing for systematic literature reviews";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in
      {
        # `nix develop` gives Python, uv, Ruff and git; uv then manages the project environment.
        devShells.default = pkgs.mkShell {
          packages = [ pkgs.python312 pkgs.uv pkgs.ruff pkgs.git ];
          shellHook = ''
            export UV_PYTHON_DOWNLOADS=never
            export UV_PYTHON=${pkgs.python312}/bin/python3
          '';
        };
      });
}
