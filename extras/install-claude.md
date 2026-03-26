# Installing Claude Code on DGX Spark

Quick-start notes for setting up Claude Code CLI on a fresh DGX Spark.

## Prerequisites

Visit https://build.nvidia.com/spark to confirm your system is registered.

## Install Claude Code

```bash
curl -fsSL https://claude.ai/install.sh | bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
claude
```

## Remote Desktop (Optional)

To set up remote access from a Mac (or other machine) on the local network, we used
[NoMachine](https://www.nomachine.com/) — fast, free, LAN-only by default.

The setup script is at `extras/setup-nomachine.sh`:

```bash
sudo extras/setup-nomachine.sh
```

This is idempotent and safe to re-run.
