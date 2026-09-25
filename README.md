# ICSPL SBP Wall Tool

A pyRevit extension for drafting SBP (secant / bored pile) walls in Revit, built for IC Singapore.

## What it does

- Draws secant pile walls with automatic HARD / SOFT pile alternation
- Draw a wall from scratch, or from selected lines and reference planes
- Keeps HARD / SOFT continuous across construction joints
- Edit an existing wall's piles with SBP Edit

## How to Install

Open **Windows PowerShell** and paste this one line, then press Enter:

    irm https://raw.githubusercontent.com/akashnethaji990-a11y/ICSPL-SBP-Wall-Tool/main/install.ps1 | iex

This installs pyRevit (if needed), downloads the tool, and sets it up automatically. Then open Revit and click **Reload** on the pyRevit tab — the **SBP** tab will appear.

For full step-by-step instructions with pictures, see the install guide PDF.

## Updating

Run the same command again any time to get the latest version, then reload pyRevit.

## Requirements

- Revit with pyRevit
- Windows
