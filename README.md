# FanPulse Agent

FanPulse Agent sends a weekly sponsor digest to end users on WhatsApp.

## Project Overview

This repository hosts the FanPulse agent, which collects sponsor-related updates and delivers a concise weekly summary to users via WhatsApp.

## Goals

- Automate weekly digest generation
- Send digest via WhatsApp messaging
- Allow customization of sponsor categories and schedule
- Support local development via a Python-based agent scaffold

## Getting Started

1. Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Run the agent starter:

```bash
python -m fanpulse_agent.main
```

## Project Structure

- `src/fanpulse_agent/` — core agent package
- `requirements.txt` — Python dependency list
- `pyproject.toml` — project metadata
- `.gitignore` — local ignores

## Notes

This is an initial scaffold. Add WhatsApp integration, sponsor data sources, and scheduling logic next.
