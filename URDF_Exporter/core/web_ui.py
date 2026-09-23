# -*- coding: utf-8 -*-
import http.server
import socketserver
import json
import threading
import webbrowser
import os
import urllib.parse

HTML_CONTENT = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>URDF Structure Editor & 3D Preview</title>
    <!-- Three.js 및 STLLoader, OrbitControls 로드 -->
    <script src="/static/three/three.min.js"></script>
    <script src="/static/three/STLLoader.js"></script>
    <script src="/static/three/OrbitControls.js"></script>
    <style>
        :root {
            --bg-dark: #1e1e1e;
            --bg-panel: #252526;
            --bg-card: #2d2d30;
            --border-color: #3e3e42;
            --accent-blue: #007acc;
            --accent-orange: #d97706;
            --accent-green: #4caf50;
            --text-main: #cccccc;
            --text-light: #ffffff;
        }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: var(--bg-dark); color: var(--text-light); padding: 0; margin: 0; display: flex; flex-direction: column; height: 100vh; overflow: hidden;}
        
        /* Header */
        .header { background: var(--bg-panel); padding: 15px 30px; display: flex; flex: 0 0 auto; flex-wrap: wrap; gap: 10px 16px; justify-content: space-between; align-items: center; position: relative; border-bottom: 1px solid var(--border-color); box-shadow: 0 2px 5px rgba(0,0,0,0.5); z-index: 100;}
        .header h2 { margin: 0; min-width: 0; font-size: 20px; white-space: nowrap;}
        .language-switcher {
            display: inline-flex; align-items: center; flex: 0 0 auto; overflow: hidden;
            padding: 3px; border: 1px solid #4b5358; border-radius: 6px; background: #202326;
        }
        .language-switcher button {
            min-width: 70px; padding: 6px 10px; border: 0; border-radius: 4px;
            background: transparent; color: #8f9aa1; font: 700 11px/1.2 'Segoe UI', sans-serif;
            letter-spacing: 0.03em; cursor: pointer;
        }
        .language-switcher button:hover { color: #e5edf1; background: #343a3e; }
        .language-switcher button.active { color: #fff; background: #356a85; }
        .language-switcher button:focus-visible { outline: 2px solid #72c7ee; outline-offset: -2px; }
        .btn { background: var(--accent-blue); color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; font-size: 14px; font-weight: bold; transition: 0.2s;}
        .btn:hover { background: #005999; }
        .header-icon-btn {
            width: 38px; height: 36px; padding: 0; display: inline-flex;
            align-items: center; justify-content: center; font-size: 18px;
            line-height: 1; border: 1px solid #464c51;
            color: #aeb5ba; background: #34383b; box-shadow: none; opacity: 0.78;
        }
        .header-icon-btn:hover {
            color: #e0e4e7; background: #41464a; border-color: #626a70; opacity: 1;
        }
        .header-icon-btn svg { width: 18px; height: 18px; display: block; }
        .header-workspace-name {
            display: none; align-items: center; gap: 7px; height: 36px;
            min-width: 0; max-width: 210px; padding: 0 10px;
            box-sizing: border-box; border: 1px solid #41484d; border-radius: 4px;
            background: #292d30; color: #a8b1b7; font-family: inherit;
            text-align: left; cursor: pointer;
        }
        .header-workspace-name.visible { display: inline-flex; }
        .header-workspace-name:hover {
            border-color: #60727d; background: #333a3e;
        }
        .header-workspace-name:focus-visible {
            outline: 2px solid rgba(39,184,255,0.65); outline-offset: 1px;
        }
        .header-workspace-label {
            flex: 0 0 auto; color: #77838a; font-size: 10px;
        }
        .header-workspace-value {
            min-width: 0; overflow: hidden; color: #edf2f5; font-size: 12px;
            font-weight: 600; text-overflow: ellipsis; white-space: nowrap;
        }
        .header-workspace-chevron {
            flex: 0 0 auto; width: 9px; height: 6px; color: #89979f;
            transition: transform 0.16s ease;
        }
        .header-workspace-switcher {
            position: relative; display: inline-flex; align-items: center;
        }
        .header-workspace-name[aria-expanded="true"] .header-workspace-chevron {
            transform: rotate(180deg);
        }
        .header-workspace-menu {
            display: none; position: absolute; top: calc(100% + 7px); left: 0;
            width: 260px; max-height: 290px; overflow-y: auto; z-index: 450;
            padding: 6px; box-sizing: border-box; border: 1px solid #505960;
            border-radius: 6px; background: #262a2d;
            box-shadow: 0 12px 28px rgba(0,0,0,0.52);
        }
        .header-workspace-menu.visible { display: block; }
        .header-workspace-menu-status {
            padding: 9px 10px; color: #8d999f; font-size: 11px; line-height: 1.4;
        }
        .header-workspace-menu-status.error { color: #ff9b9b; }
        .header-workspace-option {
            display: flex; align-items: center; justify-content: space-between;
            gap: 8px; width: 100%; min-width: 0; padding: 8px 9px;
            border: 0; border-radius: 4px; background: transparent;
            color: #dce3e7; text-align: left; cursor: pointer;
        }
        .header-workspace-option:hover { background: #343d42; }
        .header-workspace-option.active {
            background: #244858; color: #fff;
        }
        .header-workspace-option-name {
            min-width: 0; overflow: hidden; text-overflow: ellipsis;
            white-space: nowrap; font-size: 12px; font-weight: 600;
        }
        .header-workspace-option-mark {
            flex: 0 0 auto; color: #69c7ed; font-size: 11px;
        }
        #workspace-save-button .save-complete-icon { display: none; }
        #workspace-save-button.is-saving {
            color: #d9e2e7; opacity: 1; cursor: wait;
            animation: workspaceSavePulse 0.7s ease-in-out infinite alternate;
        }
        #workspace-save-button.is-saved {
            color: #fff; background: #2f7d42; border-color: #67cf7b; opacity: 1;
            box-shadow: 0 0 0 2px rgba(76,175,80,0.2);
        }
        #workspace-save-button.is-saved .save-default-icon { display: none; }
        #workspace-save-button.is-saved .save-complete-icon { display: block; }
        #workspace-save-button.is-save-error {
            color: #fff; background: #6d3434; border-color: #c96a6a; opacity: 1;
        }
        @keyframes workspaceSavePulse {
            from { opacity: 0.55; }
            to { opacity: 1; }
        }
        .export-result-page {
            min-height: 100vh; box-sizing: border-box; padding: 36px 24px;
            display: flex; align-items: center; justify-content: center;
            background:
                radial-gradient(circle at 50% 0%, rgba(76,175,80,0.08), transparent 34%),
                var(--bg-dark);
            color: #fff; overflow-y: auto;
        }
        .export-result-shell {
            width: min(880px, 100%); overflow: hidden;
            border: 1px solid #414449; border-radius: 12px;
            background: #252628; box-shadow: 0 18px 45px rgba(0,0,0,0.34);
        }
        .export-result-summary {
            display: flex; align-items: center; gap: 16px; padding: 24px 26px;
            border-bottom: 1px solid #3c4044;
        }
        .export-success-mark {
            width: 48px; height: 48px; flex: 0 0 48px; border-radius: 50%;
            display: grid; place-items: center; color: #dff7e4;
            background: #357a46; border: 1px solid #55a968;
        }
        .export-success-mark svg { width: 25px; height: 25px; }
        .export-result-summary h1 {
            margin: 0 0 5px; color: #e7f5ea; font-size: 22px; line-height: 1.25;
        }
        .export-result-summary p {
            margin: 0; color: #aeb6bc; font-size: 14px; line-height: 1.55;
        }
        .export-path-block {
            margin: 0; padding: 17px 26px; background: #202123;
            border-bottom: 1px solid #3c4044;
        }
        .export-path-label {
            margin-bottom: 7px; color: #858e95; font-size: 11px;
            font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
        }
        .export-path-value {
            color: #67b7ea; font: 600 14px/1.45 Consolas, monospace;
            word-break: break-all;
        }
        .result-section { padding: 20px 26px; }
        .result-section + .result-section { border-top: 1px solid #3c4044; }
        .result-section-heading {
            display: flex; align-items: flex-start; gap: 11px; margin-bottom: 14px;
        }
        .result-section-number {
            width: 24px; height: 24px; flex: 0 0 24px; border-radius: 6px;
            display: grid; place-items: center; color: #d4dde3;
            background: #34383c; border: 1px solid #50575d; font-size: 12px; font-weight: 700;
        }
        .result-section-title { color: #f1f3f5; font-size: 15px; font-weight: 700; }
        .result-section-subtitle { margin-top: 3px; color: #929ca3; font-size: 12px; line-height: 1.45; }
        .result-action-row { display: flex; flex-wrap: wrap; gap: 9px; margin-left: 35px; }
        .result-button {
            min-height: 38px; box-sizing: border-box; padding: 9px 15px;
            border: 1px solid #59636b; border-radius: 6px;
            background: #39434a; color: #f7f8f9; text-decoration: none;
            font: 700 13px/18px 'Segoe UI', sans-serif; cursor: pointer;
        }
        .result-button:hover:not(:disabled) { background: #46535b; border-color: #73818a; }
        .result-button.primary { background: #3d7549; border-color: #599b67; }
        .result-button.primary:hover:not(:disabled) { background: #478755; }
        .result-button.danger { background: #513030; border-color: #805050; }
        .result-button:disabled { opacity: 0.45; cursor: default; }
        .moveit-step-grid {
            display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 9px; margin-left: 35px;
        }
        .moveit-step-grid .result-button { width: 100%; }
        .result-status {
            min-height: 19px; margin: 11px 0 0 35px; color: #8fc8e8;
            font-size: 12px; line-height: 1.45;
        }
        .result-status:empty { min-height: 0; margin-top: 0; }
        .result-status.error { color: #ff8585 !important; }
        @media (max-width: 700px) {
            .export-result-page { padding: 16px 10px; align-items: flex-start; }
            .export-result-summary, .result-section, .export-path-block { padding-left: 18px; padding-right: 18px; }
            .result-action-row, .moveit-step-grid, .result-status { margin-left: 0; }
            .moveit-step-grid { grid-template-columns: 1fr; }
        }
        .btn-green { background: var(--accent-green); }
        .btn-green:hover { background: #388e3c; }
        
        /* Main Layout - Splitter Support */
        .main-content { display: flex; flex: 1; overflow: hidden; position: relative; }
        
        .left-pane { flex: 1 1 64%; display: flex; flex-direction: column; min-width: 360px; position: relative; }
        .resizer-h { height: 6px; background: #333; cursor: ns-resize; border-top: 1px solid #444; border-bottom: 1px solid #444; transition: background 0.2s; z-index: 150;}
        .resizer-h:hover { background: var(--accent-blue); }
        .resizer-v { width: 6px; flex: 0 0 6px; background: #333; cursor: ew-resize; border-left: 1px solid #444; border-right: 1px solid #444; transition: background 0.2s; z-index: 150;}
        .resizer-v:hover { background: var(--accent-blue); }
        .edit-pane {
            width: clamp(300px, 20vw, 380px);
            flex: 0 0 clamp(300px, 20vw, 380px);
            min-width: 280px; max-width: 44vw;
            display: flex; flex-direction: column; overflow: hidden;
            box-sizing: border-box; background: var(--bg-panel);
        }
        .edit-pane * { min-width: 0; box-sizing: border-box; }
        .pane-section-header {
            flex: 0 0 auto; padding: 12px 14px; font-size: 14px; font-weight: bold;
            border-bottom: 1px solid var(--border-color); overflow-wrap: anywhere;
        }
        .pane-section-header.joint-selected {
            border-bottom-color: #327b9b; background: linear-gradient(90deg, #183846 0%, #20272b 100%);
            color: #dff6ff;
        }
        .pane-body {
            flex: 1 1 50%; min-height: 160px; max-height: none; overflow: auto; padding: 12px;
            border-bottom: 1px solid var(--border-color);
        }
        .pane-section-divider {
            flex: 0 0 6px; height: 6px; background: #333;
            border-top: 1px solid #444; border-bottom: 1px solid #444;
        }
        .pane-grouping { flex: 1 1 50%; min-height: 160px; overflow: auto; padding: 12px; }
        .pane-grouping-help {
            margin: 14px 8px 6px; color: #666; text-align: center;
            font-size: 13px; font-style: italic; line-height: 1.5;
        }

        .preview-pane { height: 45%; min-height: 100px; position: relative; background: #111; overflow: hidden; flex-shrink: 0; }
        #viewer-3d-container {
            position: absolute;
            inset: 0;
            width: 100%;
            height: 100%;
            z-index: 1;
        }
        #viewer-3d-container canvas {
            display: block;
            width: 100% !important;
            height: 100% !important;
        }
        .preview-overlay {
            position: absolute;
            top: 12px;
            left: 16px;
            z-index: 20;
            color: rgba(255,255,255,0.88);
            font-weight: bold;
            pointer-events: none;
            text-shadow: 0 1px 4px rgba(0,0,0,0.8);
        }
        .tree-title-overlay { left: 20px; }
        .preview-hint {
            position: absolute;
            right: 16px;
            bottom: 14px;
            z-index: 20;
            color: rgba(255,255,255,0.68);
            font-size: 12px;
            pointer-events: none;
            text-shadow: 0 1px 4px rgba(0,0,0,0.8);
        }
        .preview-controls {
            position: absolute;
            top: 12px;
            right: 16px;
            width: 210px;
            max-height: calc(100% - 60px);
            overflow-y: auto;
            z-index: 22;
            background: rgba(20,20,20,0.78);
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 6px;
            padding: 10px;
            color: #ddd;
            font-size: 12px;
            box-sizing: border-box;
        }
        .preview-controls h3 { margin: 0 0 8px 0; font-size: 13px; color: #fff; }
        .preview-control-row { display: flex; align-items: center; gap: 6px; margin: 7px 0; cursor: pointer; }
        .preview-control-range { margin: 8px 0 10px; }
        .preview-control-range label { display: block; margin-bottom: 4px; color: #aaa; }
        .preview-control-range input[type="range"], .joint-slider { width: 100%; }
        .preview-axis-select {
            width: 100%; margin: 5px 0 8px; padding: 5px 6px; border-radius: 4px;
            border: 1px solid #555; background: #252525; color: #eee; font-size: 11px;
        }
        .ground-origin-panel {
            margin: 0 0 12px; padding: 10px; border: 1px solid rgba(55,185,235,0.55);
            border-radius: 7px; background: linear-gradient(180deg, rgba(20,91,122,0.30), rgba(16,42,54,0.24));
            box-shadow: 0 0 0 1px rgba(55,185,235,0.07) inset;
        }
        .ground-origin-panel.is-complete {
            border-color: rgba(255,255,255,0.16);
            background: rgba(255,255,255,0.035);
        }
        .ground-origin-panel.is-picking {
            border-color: #39bfff;
            box-shadow: 0 0 0 2px rgba(57,191,255,0.16), 0 0 14px rgba(24,150,210,0.16);
        }
        .ground-origin-heading {
            display: flex; align-items: center; justify-content: space-between; gap: 8px;
            margin-bottom: 8px;
        }
        .ground-origin-heading strong { color: #fff; font-size: 12px; }
        .ground-origin-state {
            flex: 0 0 auto; padding: 2px 6px; border-radius: 999px;
            background: #8a5b13; color: #ffe2a8; font-size: 9px; font-weight: 700;
        }
        .ground-origin-panel.is-complete .ground-origin-state {
            background: rgba(55,125,78,0.42); color: #acd9b8;
        }
        .ground-face-actions { display: flex; gap: 5px; margin: 3px 0 5px; }
        .ground-face-btn {
            flex: 1; min-width: 0; padding: 6px 5px; border-radius: 4px; cursor: pointer;
            border: 1px solid #666; background: #353535; color: #eee; font-size: 10px;
        }
        .ground-face-btn:hover { background: #484848; }
        .ground-face-btn.active {
            background: #0c628e; border-color: #36b9ff; color: #fff;
            box-shadow: 0 0 0 2px rgba(54,185,255,0.18);
        }
        .ground-face-btn.primary {
            width: 100%; min-height: 38px; padding: 8px 10px; border-color: #2fb8ee;
            background: #126b92; color: #fff; font-size: 12px; font-weight: 700;
        }
        .ground-face-btn.primary:hover { background: #1681ad; }
        .ground-origin-panel.is-complete:not(.is-picking) {
            display: grid; grid-template-columns: minmax(0, 1fr) auto;
            align-items: center; gap: 6px; padding: 7px 8px;
        }
        .ground-origin-panel.is-complete:not(.is-picking) .ground-origin-heading {
            justify-content: flex-start; margin: 0; min-width: 0;
        }
        .ground-origin-panel.is-complete:not(.is-picking) .ground-origin-heading strong {
            color: #c6cdd1; font-size: 10px;
        }
        .ground-origin-panel.is-complete:not(.is-picking) .ground-origin-state {
            padding: 1px 5px; font-size: 8px;
        }
        .ground-origin-panel.is-complete:not(.is-picking) .ground-face-btn.primary {
            width: auto; min-height: 25px; padding: 3px 8px;
            border-color: #4b565b; background: #30363a; color: #c8d0d4;
            font-size: 9px; font-weight: 600;
        }
        .ground-origin-panel.is-complete:not(.is-picking) .ground-face-btn.primary:hover {
            border-color: #6c7a81; background: #3a4246;
        }
        .ground-origin-panel.is-complete:not(.is-picking) .ground-face-help,
        .ground-origin-panel.is-complete:not(.is-picking) .ground-origin-secondary,
        .ground-origin-panel.is-complete:not(.is-picking) .ground-edge-toggle {
            display: none;
        }
        .ground-origin-offset {
            display: none; grid-column: 1 / -1; margin-top: 2px; padding-top: 6px;
            border-top: 1px solid rgba(255,255,255,0.10);
        }
        .ground-origin-panel.is-complete .ground-origin-offset { display: block; }
        .ground-origin-offset-title {
            display: flex; align-items: baseline; justify-content: space-between;
            gap: 6px; margin-bottom: 5px; color: #cbd5da; font-size: 9px; font-weight: 700;
        }
        .ground-origin-offset-title small { color: #87969d; font-size: 8px; font-weight: 400; }
        .ground-origin-offset-fields { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 5px; }
        .ground-origin-offset-fields label { color: #9eb0b8; font-size: 9px; }
        .ground-origin-offset-fields input {
            width: 100%; box-sizing: border-box; margin-top: 2px; padding: 4px 5px;
            border: 1px solid #4d5b62; border-radius: 4px; background: #20272b;
            color: #eef5f7; font-size: 10px; font-variant-numeric: tabular-nums;
        }
        .ground-origin-offset-fields input:focus { border-color: #39bfff; outline: none; }
        .ground-origin-secondary {
            display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 5px;
            align-items: end; margin-top: 7px;
        }
        .ground-origin-axis-label { color: #9eb0b8; font-size: 9px; }
        .ground-origin-axis-label .preview-axis-select { margin: 3px 0 0; }
        .ground-origin-reset { height: 27px; padding: 4px 7px; white-space: nowrap; }
        .ground-edge-toggle {
            display: flex; align-items: flex-start; gap: 8px; margin: 6px 0 7px;
            padding: 7px 8px; border: 1px solid rgba(255,255,255,0.14);
            border-radius: 5px; background: rgba(255,255,255,0.045);
            cursor: pointer;
        }
        .ground-edge-toggle:hover {
            border-color: rgba(88,190,235,0.55);
            background: rgba(33,116,153,0.13);
        }
        .ground-edge-toggle input {
            flex: 0 0 auto; width: 14px; height: 14px; margin: 1px 0 0;
            accent-color: #209bd2;
        }
        .ground-edge-toggle-copy {
            display: flex; min-width: 0; flex-direction: column; gap: 2px;
            line-height: 1.25;
        }
        .ground-edge-toggle-copy strong {
            color: #e9f4f9; font-size: 10px; font-weight: 600;
        }
        .ground-edge-toggle-copy small {
            color: #93a6af; font-size: 9px; line-height: 1.35;
        }
        .ground-face-help { color: #9fcbe3; font-size: 9px; line-height: 1.35; margin-bottom: 8px; }
        #viewer-3d-container.ground-face-picking canvas,
        #viewer-3d-container.joint-origin-picking canvas { cursor: crosshair !important; }
        .viewer-context-menu {
            display: none; position: fixed; z-index: 1000; min-width: 250px;
            padding: 7px; border: 1px solid #6a6a70; border-radius: 6px;
            background: #252529; color: #eee; box-shadow: 0 10px 28px rgba(0,0,0,0.55);
        }
        .viewer-context-menu.visible { display: block; }
        .viewer-context-title {
            padding: 6px 8px 8px; color: #b9c3cc; font-size: 11px;
            border-bottom: 1px solid #414147; margin-bottom: 5px;
        }
        .viewer-context-menu button {
            width: 100%; padding: 8px 10px; border: 0; border-radius: 4px;
            background: transparent; color: #fff; text-align: left; cursor: pointer;
            font-size: 12px;
        }
        .viewer-context-menu button:hover:not(:disabled) { background: #174b61; }
        .viewer-context-menu button:disabled { color: #73737a; cursor: default; }
        .preview-subhead { margin-top: 10px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.12); font-weight: bold; color: #fff; }
        .preview-actions { display: flex; gap: 6px; margin: 8px 0; }
        .mini-btn { flex: 1; background: #3b3b3b; color: #eee; border: 1px solid #555; border-radius: 4px; padding: 5px; cursor: pointer; font-size: 11px; }
        .mini-btn:hover { background: #4a4a4a; }
        .joint-control { margin-top: 10px; padding: 8px 5px 0; border-top: 1px solid rgba(255,255,255,0.1); border-radius: 5px; }
        .joint-control.is-selected {
            background: rgba(36, 139, 190, 0.13);
            box-shadow: inset 3px 0 #31bdf5;
        }
        .joint-title, .joint-value-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
        .joint-name-button {
            min-width: 0; padding: 2px 4px; border: 0; border-radius: 3px;
            background: transparent; color: #e8edf0; cursor: pointer;
            font: inherit; text-align: left;
        }
        .joint-name-button:hover,
        .joint-name-button:focus-visible {
            color: #73d8ff; background: rgba(49, 189, 245, 0.13); outline: none;
        }
        .joint-control.is-selected .joint-name-button { color: #79ddff; font-weight: 700; }
        .joint-details-toggle {
            display: grid; grid-template-columns: 1fr 28px 1fr;
            align-items: center; gap: 6px; width: 100%; height: 24px;
            margin: 5px 0 1px; padding: 0; border: 0;
            background: transparent; color: #b8c4ca; cursor: pointer;
        }
        .joint-details-toggle::before,
        .joint-details-toggle::after {
            content: ''; height: 1px; background: rgba(255,255,255,0.12);
        }
        .joint-details-toggle:hover::before,
        .joint-details-toggle:hover::after {
            background: rgba(65,181,232,0.5);
        }
        .joint-details-arrow {
            display: grid; place-items: center; width: 28px; height: 18px;
            box-sizing: border-box; border: 1px solid #53616a; border-radius: 9px;
            background: #30373b; transition: 0.16s ease;
        }
        .joint-details-arrow svg {
            width: 12px; height: 7px; display: block;
        }
        .joint-details-toggle:hover .joint-details-arrow {
            color: #e9f8ff; border-color: #37afe3; background: #244b5d;
        }
        .joint-details { display: none; }
        .joint-control.details-expanded .joint-details { display: block; }
        .joint-control.details-expanded .joint-details-arrow svg { transform: rotate(180deg); }
        .joint-fine-control { display: flex; align-items: center; justify-content: center; gap: 4px; }
        .joint-fine-control button {
            width: 28px; height: 21px; padding: 0; border: 1px solid #555; border-radius: 3px;
            background: #343434; color: #eee; cursor: pointer; font-size: 10px; font-weight: bold;
        }
        .joint-fine-control button:hover { border-color: #27b8ff; background: #174b61; }
        .joint-fine-control .joint-value { min-width: 34px; text-align: center; }
        .joint-current-input {
            width: 58px;
            min-width: 58px;
            box-sizing: border-box;
            border: 1px solid #56616a;
            border-radius: 3px;
            background: #15191c;
            color: #fff;
            padding: 2px 4px;
            text-align: center;
            font: inherit;
        }
        .joint-current-input:focus {
            outline: none;
            border-color: #27b8ff;
            box-shadow: 0 0 0 1px rgba(39, 184, 255, 0.3);
        }
        .joint-badge-ui { color: #ffb74d; font-size: 10px; }
        .joint-edit-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px; margin-top: 6px; }
        .joint-edit-row label { display: flex; align-items: center; gap: 3px; color: #aaa; font-size: 10px; }
        .joint-rpy-input { width: 100%; min-width: 0; box-sizing: border-box; background: #252525; border: 1px solid #555; color: #eee; border-radius: 3px; padding: 3px 4px; font-size: 10px; }
        .joint-limit-editor {
            margin: 8px 0; padding: 7px; border: 1px solid rgba(255,184,77,0.34);
            border-radius: 5px; background: rgba(85,51,12,0.2);
        }
        .joint-limit-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; }
        .joint-limit-actions button {
            min-width: 0; padding: 6px 4px; border: 1px solid #956321; border-radius: 4px;
            background: #493216; color: #ffe0ad; cursor: pointer; font-size: 10px;
        }
        .joint-limit-actions button:hover { background: #62451f; border-color: #e6a23c; }
        .joint-limit-inputs {
            display: grid; grid-template-columns: 1fr 1fr; gap: 5px; margin-top: 6px;
        }
        .joint-limit-inputs label {
            display: flex; align-items: center; gap: 4px; min-width: 0;
            color: #c8c8c8; font-size: 9px;
        }
        .joint-limit-inputs input {
            width: 100%; min-width: 0; padding: 4px; box-sizing: border-box;
            border: 1px solid #6d562f; border-radius: 3px; background: #25231f;
            color: #ffe0ad; font-size: 10px;
        }
        .joint-limit-summary {
            display: flex; justify-content: space-between; gap: 5px; margin-top: 6px;
            color: #ffd18e; font-size: 9px; font-variant-numeric: tabular-nums;
        }
        .joint-limit-summary.pending { color: #ff9f7a; }
        .joint-parameter-heading {
            display: flex; align-items: center; justify-content: space-between; gap: 8px;
            margin-bottom: 7px; color: #ffe0ad; font-size: 10px; font-weight: 700;
        }
        .joint-parameter-heading span {
            color: #c7a86f; font-size: 9px; font-weight: 600;
        }
        .joint-required-inputs {
            display: grid; grid-template-columns: 1fr 1fr; gap: 5px; margin-top: 7px;
            padding-top: 7px; border-top: 1px solid rgba(255,184,77,0.18);
        }
        .joint-required-inputs label {
            display: flex; flex-direction: column; gap: 3px; min-width: 0;
            color: #c8c8c8; font-size: 9px;
        }
        .joint-required-inputs input {
            width: 100%; min-width: 0; padding: 4px; box-sizing: border-box;
            border: 1px solid #6d562f; border-radius: 3px; background: #25231f;
            color: #ffe0ad; font-size: 10px;
        }
        .joint-fixed-settings {
            margin: 8px 0 12px; padding: 9px; border: 1px solid rgba(255,255,255,0.14);
            border-radius: 5px; background: rgba(255,255,255,0.035);
            color: #aeb8bd; font-size: 10px;
        }
        .joint-property-card {
            margin-bottom: 12px; padding: 10px; border: 1px solid #47545b;
            border-radius: 7px; background: #20282c;
        }
        .joint-origin-toolbox {
            margin-bottom: 10px; padding: 9px; border: 1px solid #397f9d;
            border-left: 3px solid #44cbff; border-radius: 6px;
            background: linear-gradient(180deg, #172e38 0%, #1d292f 100%);
            box-shadow: 0 4px 10px rgba(0,0,0,0.22);
        }
        .joint-origin-toolbox .hint-box { margin: 0 0 8px !important; padding: 8px; }
        .joint-selection-hero {
            display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 3px 8px;
            align-items: center; margin-bottom: 10px; padding: 10px;
            border: 1px solid #4a606b; border-radius: 7px; background: #222d32;
        }
        .joint-selection-badge {
            grid-row: 1 / 3; padding: 5px 7px; border-radius: 5px;
            background: #116b91; color: #fff; font-size: 9px; font-weight: 800;
        }
        .joint-selection-hero strong {
            min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
            color: #fff; font-size: 13px;
        }
        .joint-selection-hero small {
            min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
            color: #9fc4d3; font-size: 9px;
        }
        .joint-property-title { margin-bottom: 10px; color: #f4f8fa; font-size: 13px; font-weight: 800; }
        .joint-property-section { padding: 9px 0; border-top: 1px solid rgba(255,255,255,0.09); }
        .joint-property-section:first-of-type { border-top: 0; padding-top: 0; }
        .joint-property-section-title {
            margin-bottom: 7px; color: #77d5ff; font-size: 9px; font-weight: 800; letter-spacing: 1px;
        }
        .joint-property-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; }
        .joint-property-grid.three { grid-template-columns: repeat(3, minmax(0, 1fr)); }
        .joint-property-grid label { min-width: 0; color: #9fadb4; font-size: 9px; }
        .joint-general-spacer { min-height: 1px; }
        .joint-property-grid input, .joint-property-grid select { margin-top: 3px; }
        .joint-property-readonly {
            padding: 6px 7px; border: 1px solid #3f4b51; border-radius: 4px;
            background: #1a2023; color: #cbd5da; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
            font-size: 10px;
        }
        .joint-property-details { margin-top: 7px; border: 1px solid #3f4c52; border-radius: 5px; background: #1c2326; }
        .joint-property-details > summary { padding: 7px 8px; color: #c8d5da; font-size: 10px; font-weight: 700; cursor: pointer; }
        .joint-property-details-body { padding: 0 8px 8px; }
        .joint-interface-checks { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 7px; }
        .joint-interface-checks label { color: #c3d0d5; font-size: 10px; }
        .joint-cad-transform-button {
            width: 100%; margin-top: 7px; cursor: pointer; border-color: #587385;
            background: #273943; color: #e8f7ff;
        }
        .viz-pane { flex: 1; position: relative; overflow: auto; background-image: radial-gradient(#333 1px, transparent 1px); background-size: 20px 20px; padding: 20px; min-height: 100px;}
        
        /* Tree CSS - 간격 축소 및 중앙 정렬 */
        .tree { display: flex; justify-content: center; min-width: 100%; padding-bottom: 100px; }
        .tree ul { padding-top: 25px; position: relative; display: flex; justify-content: center; padding-left: 0; margin: 0; min-width: max-content; }
        .tree li { text-align: center; list-style-type: none; position: relative; padding: 25px 5px 0 5px; display: flex; flex-direction: column; align-items: center;}
        .tree li::before, .tree li::after { content: ''; position: absolute; top: 0; right: 50%; border-top: 2px solid #666; width: 50%; height: 25px; z-index: 1; }
        .tree li::after { right: auto; left: 50%; border-left: 2px solid #666; }
        .tree li:only-child::before, .tree li:only-child::after { display: none; }
        .tree li:only-child { padding-top: 0; }
        .tree li:first-child::before, .tree li:last-child::after { border: 0 none; }
        .tree li:last-child::before { border-right: 2px solid #666; border-radius: 0 8px 0 0; }
        .tree li:first-child::after { border-radius: 8px 0 0 0; }
        .tree ul ul::before { content: ''; position: absolute; top: 0; left: 50%; border-left: 2px solid #666; width: 0; height: 25px; z-index: 1; }
        .compact-child-summary {
            margin: 14px auto 10px; padding: 6px 12px; border-radius: 14px;
            background: rgba(0,122,204,0.18); border: 1px solid rgba(0,170,255,0.5);
            color: #b9e6ff; font-size: 11px; font-weight: bold; z-index: 12;
        }
        .tree ul.compact-children {
            display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 18px 14px; width: min(820px, calc(100vw - 500px)); min-width: 0;
            padding: 12px; margin: 0 auto; border: 1px dashed #3f596d;
            border-radius: 10px; background: rgba(16,29,40,0.68);
        }
        .tree ul.compact-children::before,
        .tree ul.compact-children > li::before,
        .tree ul.compact-children > li::after { display: none; }
        .tree ul.compact-children > li { padding: 0; min-width: 0; width: 100%; }
        .tree ul.compact-children > li > .node-wrapper { width: 100%; }
        .tree ul.compact-children > li .joint-badge {
            position: relative; top: auto; width: calc(100% - 12px); max-width: 210px;
            margin: 0 auto 5px; padding: 3px 7px; overflow: hidden;
            text-overflow: ellipsis; display: block; white-space: nowrap;
            background: #74440e; border-width: 1px; font-size: 9px;
        }
        .tree ul.compact-children > li .link-box {
            width: 100%; min-width: 0; max-width: 220px; padding: 8px 10px;
            box-sizing: border-box;
        }
        .tree ul.compact-children > li .link-name span:last-child {
            overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        }
        .tree.patcher-mode {
            display: block; min-width: 0; width: 100%; height: 100%; padding: 0;
        }
        .patcher-shell {
            position: relative; min-width: 100%; height: 100%; min-height: 340px;
            padding-top: 24px; box-sizing: border-box;
        }
        .patcher-controls {
            position: sticky; top: 0; left: 0; z-index: 80; overflow: visible;
            border-radius: 7px; background: #1b1b1d;
            box-shadow: 0 4px 10px rgba(0,0,0,0.3);
        }
        .patcher-toolbar {
            position: relative; z-index: 2; display: flex; align-items: center;
            gap: 8px; min-height: 36px; padding: 7px 10px; box-sizing: border-box;
            background: rgba(27,27,29,0.96); border: 1px solid #3d3d42; border-radius: 7px;
            box-shadow: none;
        }
        .patcher-controls.material-shelf-open .patcher-toolbar { border-radius: 7px; }
        .patcher-toolbar button {
            border: 1px solid #56565d; background: #34343a; color: #eee; border-radius: 4px;
            padding: 5px 9px; cursor: pointer; font-size: 10px; font-weight: bold;
        }
        .patcher-toolbar button:hover { background: #45454d; border-color: #1da1f2; }
        .patcher-toolbar button.material-shelf-active {
            border-color: #4fb8e5; color: #dff7ff; background: #174056;
            box-shadow: inset 0 0 0 1px rgba(83,207,255,0.13), 0 0 8px rgba(83,207,255,0.18);
        }
        .patcher-toolbar button.needs-attention {
            color: #ffe2a6; border-color: #a97927; background: #4a3c25;
            box-shadow: 0 0 7px rgba(226,166,58,0.42), inset 0 0 5px rgba(255,204,92,0.08);
        }
        .patcher-toolbar button.needs-attention:hover {
            color: #fff0c9; border-color: #d39b39; background: #594727;
        }
        .patcher-summary { margin-left: auto; color: #b9c3cc; font-size: 10px; }
        .patcher-material-shelf {
            position: absolute; z-index: 95; top: calc(100% + 7px); left: 0; right: auto;
            width: min(350px, calc(100vw - 48px)); max-height: min(330px, calc(100vh - 190px));
            box-sizing: border-box; margin: 0; padding: 10px;
            border: 1px solid #4d7e93; border-radius: 8px;
            background: linear-gradient(180deg, #22333b 0%, #1d292f 100%);
            box-shadow: 0 14px 32px rgba(0,0,0,0.58), inset 0 5px 12px rgba(0,0,0,0.12);
        }
        .patcher-material-shelf[hidden] { display: none; }
        .patcher-material-shelf-head {
            display: grid; grid-template-columns: 1fr auto; gap: 5px 8px;
            align-items: center; margin-bottom: 8px;
        }
        .patcher-material-shelf-head strong { color: #dcf5ff; font-size: 11px; white-space: nowrap; }
        .patcher-material-shelf-search {
            grid-column: 1 / -1; width: 100%; min-width: 0; height: 28px; box-sizing: border-box;
            padding: 3px 7px; border: 1px solid #4c7c91; border-radius: 4px;
            background: #16242a; color: #eefaff; font-size: 11px;
        }
        .patcher-material-shelf-search:focus { outline: none; border-color: #53cfff; }
        .patcher-material-shelf-hint { color: #8eb4c4; font-size: 8px; white-space: nowrap; }
        .patcher-material-shelf-cards {
            display: flex; flex-direction: column; flex-wrap: nowrap; gap: 5px; max-width: 100%;
            max-height: 220px; overflow-x: hidden; overflow-y: auto;
            padding: 1px 3px 2px 1px;
            scrollbar-width: none;
        }
        .patcher-material-shelf-cards::-webkit-scrollbar { width: 0; height: 0; }
        .patcher-material-card {
            display: flex; flex: 0 0 auto; width: 100%; align-items: center; gap: 7px;
            min-width: 0; min-height: 40px; box-sizing: border-box; padding: 6px 8px;
            border: 1px solid #40545e; border-radius: 5px; background: #29353a;
            color: #edf8fc; cursor: grab; user-select: none;
        }
        .patcher-material-card:hover {
            border-color: #5dcdfb; background: #234655; box-shadow: 0 0 7px rgba(83,207,255,0.2);
        }
        .patcher-material-card.dragging { opacity: 0.5; }
        .patcher-material-card .material-drag-copy strong { font-size: 10px; }
        .patcher-material-card .material-drag-copy small { font-size: 8px; }
        .patcher-material-add-card {
            min-height: 36px; justify-content: center; border-style: dashed;
            border-color: #4f91aa; color: #9ddfff; background: rgba(31,76,94,0.32);
            font-size: 11px; font-weight: bold; cursor: pointer;
        }
        .patcher-material-add-card:hover {
            border-color: #69d6ff; color: #e7faff; background: rgba(35,111,140,0.42);
        }
        .patcher-material-add-card span:first-child { font-size: 18px; line-height: 1; }
        .patcher-material-create {
            flex: 0 0 auto; width: 100%; display: grid;
            grid-template-columns: minmax(0, 1fr) minmax(105px, 0.65fr);
            gap: 7px; align-items: end; box-sizing: border-box; padding: 8px;
            border: 1px solid #4d849b;
            border-radius: 6px; background: #1b3039;
        }
        .patcher-material-create label {
            display: flex; flex-direction: column; gap: 3px; min-width: 0;
            color: #a9c2cd; font-size: 9px;
        }
        .patcher-material-create input {
            width: 100%; height: 28px; box-sizing: border-box; padding: 4px 7px;
            border: 1px solid #4c6976; border-radius: 4px; background: #17262c;
            color: #f2fbff; font-size: 11px;
        }
        .patcher-material-create input[type="color"] { padding: 3px; cursor: pointer; }
        .patcher-material-create-actions { display: flex; gap: 5px; }
        .patcher-material-create-actions { grid-column: 1 / -1; }
        .patcher-material-create-actions button {
            height: 28px; padding: 4px 10px; border: 1px solid #4d7180; border-radius: 4px;
            background: #2b424c; color: #eaf9ff; cursor: pointer; font-size: 10px;
        }
        .patcher-material-create-actions button:first-child {
            border-color: #3b9b6a; background: #1e533b; color: #d8ffea;
        }
        .patcher-material-empty { padding: 18px 8px; color: #91a9b4; text-align: center; font-size: 10px; }
        .patcher-zoom-readout {
            min-width: 42px; color: #8fd8ff; font-size: 10px; text-align: center;
            font-variant-numeric: tabular-nums;
        }
        .patcher-validation {
            position: absolute; top: 8px; left: 8px; right: 8px; z-index: 75;
            margin: 0; padding: 7px 10px; border-radius: 5px; font-size: 10px;
            border: 1px solid rgba(178,126,35,0.72); color: #ffe0a3;
            background: rgba(66,45,12,0.58); backdrop-filter: blur(2px);
            box-shadow: 0 2px 8px rgba(0,0,0,0.18); pointer-events: none;
        }
        .patcher-validation.ok {
            border-color: rgba(61,157,83,0.72); color: #b5edc0; background: rgba(20,78,37,0.52);
        }
        .patcher-viewport {
            position: relative; width: 100%; height: calc(100% - 54px); min-height: 245px;
            margin-top: 8px; overflow: hidden; border: 1px solid #313a42; border-radius: 8px;
            background-color: #3d454a; cursor: grab; touch-action: none;
            background-image:
                radial-gradient(rgba(255,255,255,0.11) 1px, transparent 1px);
            background-size: 28px 28px;
            background-position: var(--patcher-grid-x, 0px) var(--patcher-grid-y, 0px);
        }
        .patcher-viewport.panning { cursor: grabbing; }
        .patcher-canvas {
            position: absolute; left: 0; top: 0; width: 4200px; height: 2600px;
            transform-origin: 0 0; overflow: visible;
        }
        .patcher-node, .patcher-joint-label {
            text-rendering: geometricPrecision;
            -webkit-font-smoothing: antialiased;
        }
        .patcher-cables {
            position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible;
            z-index: 2; pointer-events: none;
        }
        .patcher-cable {
            fill: none; stroke: #ffd22e; stroke-width: 3; opacity: 0.94;
            filter: drop-shadow(0 0 3px rgba(245,158,11,0.45)); pointer-events: stroke;
            cursor: pointer;
        }
        .patcher-cable.revolute, .patcher-cable.continuous { stroke: #40e1c1; }
        .patcher-cable.prismatic { stroke: #48a9ff; }
        .patcher-cable.world { stroke: #40e1c1; }
        .patcher-cable.selected { stroke-width: 6; filter: drop-shadow(0 0 6px #00aaff); }
        .patcher-temp-cable { fill: none; stroke: #76cfff; stroke-width: 3; stroke-dasharray: 6 5; }
        .patcher-node {
            position: absolute; width: 176px; z-index: 12; user-select: none;
            border-radius: 5px; box-shadow: 0 6px 13px rgba(0,0,0,0.38);
        }
        .patcher-node .link-box {
            width: 100%; min-width: 0; box-sizing: border-box; padding: 7px 9px;
            border-radius: 4px; border-top-width: 3px; background: #30363a;
        }
        .patcher-node.disconnected .link-box {
            border-color: #8b5d1b; border-top-color: #d68b1c; background: #302719;
        }
        .patcher-node .link-box.finalized,
        .patcher-node.disconnected .link-box.finalized {
            border-color: #008fd4; border-top-color: #27b8ff; background: #173244;
        }
        .patcher-node.group-selected .link-box {
            border-color: #d95cff !important; border-top-color: #d95cff !important;
            box-shadow: 0 0 0 3px rgba(217,92,255,0.28), 0 0 16px rgba(217,92,255,0.55);
        }
        .patcher-node.group-target .link-box {
            border-color: #62e68b !important; border-top-color: #62e68b !important;
        }
        .patcher-node.merge-dragging {
            z-index: 45; opacity: 0.82;
        }
        .patcher-node.merge-drop-target .link-box {
            border-color: #62e68b !important; border-top-color: #62e68b !important;
            box-shadow: 0 0 0 4px rgba(98,230,139,0.28), 0 0 20px rgba(98,230,139,0.72);
        }
        .patcher-node.world-node {
            width: 176px; height: 72px; min-height: 72px; padding: 10px;
            box-sizing: border-box; text-align: center;
            border: 1px solid #1b2327; background: #2b3135; color: #fff; font-weight: bold;
        }
        .patcher-node.world-node.disconnected-world {
            border-color: #bd8129; color: #ffe1a8;
        }
        .patcher-node.world-node.world-disabled {
            opacity: 0.32; filter: grayscale(0.75); box-shadow: none;
        }
        .patcher-node.world-node.footprint-with-settings {
            border-bottom-left-radius: 0; border-bottom-right-radius: 0;
            border-color: rgba(92,190,122,0.46);
            border-bottom-color: transparent;
            background: linear-gradient(180deg, #2b3337 0%, #293237 100%);
            box-shadow: 0 6px 13px rgba(0,0,0,0.24);
        }
        .patcher-node.world-node.base-footprint-selected {
            border-color: #58e8a0;
            box-shadow: 0 0 0 3px rgba(88,232,160,0.24), 0 0 18px rgba(88,232,160,0.42);
        }
        .patcher-footprint-settings {
            position: absolute; left: 42px; top: 126px; z-index: 20; width: 176px;
            box-sizing: border-box; padding: 9px; border: 1px solid #4b5960;
            border-top: 0; border-radius: 0 0 7px 7px; color: #dce5e9;
            background: linear-gradient(180deg, #263035 0%, #222a2e 100%);
            box-shadow: inset 0 8px 12px rgba(0,0,0,0.07), 0 7px 13px rgba(0,0,0,0.26);
        }
        .patcher-footprint-settings {
            border-color: rgba(92,190,122,0.46);
            border-top-color: transparent;
        }
        .patcher-footprint-settings.base-footprint-selected {
            border-color: #58e8a0;
            border-top-color: transparent;
            box-shadow: 0 8px 18px rgba(88,232,160,0.22);
        }
        .patcher-footprint-settings-heading {
            display: flex; align-items: center; justify-content: space-between; gap: 5px;
            margin: 0 -2px 7px; padding: 1px 2px 6px;
            border-bottom: 1px solid rgba(170,205,190,0.11);
            color: #d7e7e0; font-size: 9px; font-weight: 700;
        }
        .patcher-footprint-settings-heading span:last-child { color: #9fb4ac; font-size: 8px; }
        .patcher-footprint-offset-title {
            display: flex; justify-content: space-between; margin-bottom: 4px;
            color: #cbd5da; font-size: 8px; font-weight: 700;
        }
        .patcher-footprint-offset-fields { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 4px; }
        .patcher-footprint-offset-fields label { color: #9eb0b8; font-size: 8px; }
        .patcher-footprint-offset-fields input {
            width: 100%; box-sizing: border-box; margin-top: 2px; padding: 3px 4px;
            border: 1px solid #4d5b62; border-radius: 4px; background: #1d2428;
            color: #eef5f7; font-size: 9px;
        }
        .patcher-world-fix {
            position: absolute; left: 42px; top: 22px; z-index: 18;
            width: 176px; height: 32px; box-sizing: border-box;
            display: flex; align-items: center; justify-content: center; gap: 5px;
            border: 1px solid #555; border-radius: 5px 5px 0 0; background: #303438;
            color: #aaa; font-size: 11px; font-weight: bold; cursor: pointer;
            transition: opacity 0.2s, background 0.2s, border-color 0.2s;
        }
        .patcher-world-fix.checked-state {
            color: #fff; border-color: var(--accent-green);
            background: rgba(76,175,80,0.2); box-shadow: 0 0 7px rgba(76,175,80,0.3);
        }
        .patcher-world-fix input { margin: 0; }
        .patcher-world-fix select {
            width: 164px; height: 24px; padding: 2px 6px; border: 1px solid #59666c;
            border-radius: 4px; background: #20272b; color: #eef5f7; font-size: 10px;
            cursor: pointer;
        }
        .patcher-world-fix + .patcher-node.world-node {
            border-top-left-radius: 0; border-top-right-radius: 0;
        }
        .patcher-node-header {
            display: flex; align-items: center; gap: 5px; cursor: move; margin: -3px -5px 5px;
            padding: 4px 5px; border-radius: 3px; background: rgba(0,0,0,0.18);
        }
        .patcher-node-title {
            min-width: 0; flex: 1; overflow: hidden; white-space: nowrap; text-overflow: ellipsis;
            font-size: 11px; font-weight: bold;
        }
        .patcher-node-rename {
            flex: 0 0 auto; width: 18px; height: 18px; padding: 0; border-radius: 3px;
            border: 1px solid transparent; color: #8ed8ff; background: transparent;
            cursor: pointer; font-size: 10px; line-height: 16px;
        }
        .patcher-node-rename:hover { border-color: #27b8ff; background: #173f55; color: #fff; }
        .patcher-node-ungroup {
            flex: 0 0 auto; height: 18px; padding: 0 5px; border-radius: 3px;
            border: 1px solid transparent; color: #ffd18e; background: transparent;
            cursor: pointer; font-size: 9px; line-height: 16px;
        }
        .patcher-node-ungroup:hover {
            border-color: #e6a23c; background: #4a3216; color: #fff;
        }
        .patcher-node-toggle {
            flex: 0 0 auto; width: 24px; height: 14px; padding: 2px; border-radius: 999px;
            border: 1px solid #16a34a; background: #22c55e;
            cursor: pointer; box-sizing: border-box; display: inline-flex;
            align-items: center; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            user-select: none;
        }
        .patcher-node-toggle .toggle-knob {
            width: 8px; height: 8px; border-radius: 50%;
            background: #ffffff; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.4);
            transform: translateX(10px);
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); flex-shrink: 0;
        }
        .patcher-node-toggle:hover {
            box-shadow: 0 0 6px rgba(34, 197, 94, 0.7); transform: scale(1.08);
        }
        .patcher-node-toggle.is-disabled {
            border-color: #555e68; background: #374151;
        }
        .patcher-node-toggle.is-disabled .toggle-knob {
            background: #9ca3af;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.4);
            transform: translateX(0px);
        }
        .patcher-node-toggle.is-disabled:hover {
            border-color: #ef4444; background: #4b2328;
            box-shadow: 0 0 6px rgba(239, 68, 68, 0.5); transform: scale(1.08);
        }
        .patcher-node-toggle.is-disabled:hover .toggle-knob {
            background: #fca5a5;
        }
        .patcher-node.disabled {
            opacity: 0.45;
        }
        .patcher-node.disabled:hover {
            opacity: 0.85;
        }
        .patcher-node.disabled .link-box,
        .link-box.disabled {
            border-color: #555e66 !important;
            border-top-color: #77838d !important;
            background: #1c2024 !important;
            box-shadow: none !important;
            opacity: 0.6;
        }
        .joint-badge.disabled {
            opacity: 0.6;
            background: #25282d !important;
            border-color: #586068 !important;
            color: #9aa3ab !important;
            text-decoration: line-through;
        }
        .patcher-node-state.disabled-state {
            color: #ff7b7b !important;
            font-weight: bold;
        }
        .patcher-cable.disabled {
            stroke: #606872 !important;
            stroke-dasharray: 6 4 !important;
            opacity: 0.48 !important;
            filter: none !important;
        }
        .patcher-joint-label.disabled {
            opacity: 0.6;
            background: #25282d !important;
            border-color: #586068 !important;
            color: #9aa3ab !important;
            text-decoration: line-through;
        }
        .list-link-item.disabled {
            opacity: 0.5;
            background: #22252a;
        }
        .patcher-node-name-input {
            min-width: 0; flex: 1; height: 20px; box-sizing: border-box; padding: 1px 4px;
            border: 1px solid #27b8ff; border-radius: 3px; color: #fff; background: #142a36;
            font-size: 11px; font-weight: bold; outline: none;
        }
        .patcher-node-state { font-size: 9px; color: #aab2ba; }
        .patcher-node.disconnected .patcher-node-state { color: #ffc66d; }
        .patcher-port {
            position: absolute; top: 29px; width: 13px; height: 13px; padding: 0;
            border-radius: 50%; border: 2px solid #172126; background: #2f93c9; z-index: 30;
            cursor: crosshair; box-shadow: 0 0 0 1px rgba(255,255,255,0.42);
        }
        .patcher-port:hover { transform: scale(1.18); background: #6dd0ff; }
        .patcher-port.input { left: -7px; background: #40e1c1; }
        .patcher-port.output { right: -7px; background: #40e1c1; }
        .patcher-port.output.connected-output {
            background: #40e1c1; border-color: #123c35;
        }
        .patcher-port.output.add-output {
            display: flex; align-items: center; justify-content: center;
            background: #2388bc; border-color: #102f40; color: #fff;
            font-size: 11px; font-weight: bold; line-height: 1;
        }
        .patcher-port.output.add-output:hover {
            background: #39baf5; box-shadow: 0 0 0 4px rgba(57,186,245,0.25);
        }
        .patcher-port.connect-target { box-shadow: 0 0 0 5px rgba(75,219,125,0.35); }
        .patcher-joint-label {
            position: absolute; z-index: 18; transform: translate(-50%, -50%);
            max-width: 150px; padding: 3px 7px; border-radius: 10px; cursor: pointer;
            border: 1px solid #927b1a; background: #4e481a; color: #fff; font-size: 8px;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .patcher-joint-label:hover, .patcher-joint-label.selected {
            border-color: #50c5ff; box-shadow: 0 0 9px rgba(0,170,255,0.7);
        }
        .patcher-joint-label.controller-pick {
            border-color: #d95cff; background: #54235f;
            box-shadow: 0 0 0 3px rgba(217,92,255,0.24), 0 0 12px rgba(217,92,255,0.7);
        }
        .patcher-controller-frame {
            position: absolute; z-index: 8; box-sizing: border-box; pointer-events: none;
            border: 2px solid var(--controller-color, #d95cff); border-radius: 14px;
            background: var(--controller-fill, rgba(217,92,255,0.14));
            box-shadow: inset 0 0 22px var(--controller-glow, rgba(217,92,255,0.12)),
                        0 0 10px var(--controller-glow, rgba(217,92,255,0.28));
        }
        .patcher-controller-frame.selected {
            border-width: 3px;
            box-shadow: inset 0 0 28px var(--controller-fill), 0 0 18px var(--controller-color);
        }
        .patcher-controller-label {
            position: absolute; left: 12px; top: -13px; height: 24px; max-width: 210px;
            padding: 2px 10px; border: 1px solid var(--controller-color, #d95cff); border-radius: 12px;
            background: var(--controller-label, #4b1f57); color: #fff; font-size: 9px; font-weight: 800;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
            cursor: pointer; pointer-events: auto;
        }
        .patcher-controller-label:hover { border-color: #8fe9ff; background: #234c60; }
        .patcher-controller-label.selected,
        .patcher-controller-frame.selected .patcher-controller-label {
            border-color: #ffffff; border-width: 2px;
            box-shadow: 0 0 10px var(--controller-color, #d95cff), 0 0 4px #ffffff;
            filter: brightness(1.25);
        }
        .patcher-controller-frame.label-bottom .patcher-controller-label {
            top: auto; bottom: -13px;
        }
        .patcher-empty-note {
            position: absolute; left: 32px; top: 132px; width: 220px; color: #98a1aa;
            font-size: 11px; line-height: 1.5; padding: 10px; border: 1px dashed #4b535a;
            border-radius: 6px; background: rgba(0,0,0,0.22);
        }

        /* Joint Badge - 한 줄 유지 */
        .joint-badge {
            background: var(--accent-orange); color: white;
            padding: 4px 12px; border-radius: 12px; font-size: 11px; font-weight: bold;
            position: absolute; top: -18px; z-index: 10;
            border: 2px solid #9c5404;
            display: flex; align-items: center; gap: 5px;
            white-space: nowrap;
        }
        .joint-badge:hover { background: #f59e0b; }
        .joint-badge.group-candidate {
            background: #185c73; border-color: #38bdf8; color: #d9f4ff;
        }
        .joint-badge.group-candidate:hover { background: #247895; }
        
        /* Link Box */
        .link-box {
            border: 2px solid #444; border-top: 6px solid var(--accent-blue); border-radius: 6px;
            padding: 10px 15px; background: var(--bg-card); min-width: 100px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3); position: relative; z-index: 10;
        }
        .link-box:hover { border-color: var(--accent-blue); }
        .link-box.finalized { border-color: var(--accent-green); border-top-color: var(--accent-green); background: #1b3320; }
        .link-box.selected {
            border-color: #00aaff !important;
            box-shadow: 0 0 0 3px rgba(0,170,255,0.28), 0 0 22px rgba(0,170,255,0.8) !important;
            animation: selectedLinkPulse 1.15s ease-in-out infinite;
        }
        .joint-badge.selected { box-shadow: 0 0 18px rgba(0,170,255,0.9); }
        .tree-wire-layer {
            position: absolute; left: 0; top: 0; z-index: 6;
            overflow: visible; pointer-events: none;
        }
        .tree-wire {
            fill: none; stroke: #40e1c1; stroke-width: 4;
            filter: drop-shadow(0 0 4px rgba(64,225,193,0.48));
            pointer-events: stroke; cursor: pointer;
        }
        .tree-wire.fixed { stroke: #ffd22e; }
        .tree-wire.prismatic { stroke: #48a9ff; }
        .tree-wire.selected { stroke-width: 7; filter: drop-shadow(0 0 7px #00aaff); }
        .tree-wire-temp {
            fill: none; stroke: #76cfff; stroke-width: 3;
            stroke-dasharray: 7 6; pointer-events: none;
        }
        .tree-wire-port {
            position: absolute; top: 50%; width: 15px; height: 15px;
            padding: 0; transform: translateY(-50%); border-radius: 50%;
            border: 2px solid #13242b; background: #40e1c1; z-index: 30;
            cursor: crosshair; box-shadow: 0 0 0 1px rgba(255,255,255,0.55);
        }
        .tree-wire-port:hover { transform: translateY(-50%) scale(1.22); background: #75f4dc; }
        .tree-wire-port.input { left: -9px; }
        .tree-wire-port.output { right: -9px; }
        .tree-wire-port.connect-target {
            box-shadow: 0 0 0 5px rgba(75,219,125,0.38), 0 0 13px #40e1c1;
        }
        .tree-wire-help {
            position: sticky; top: 0; z-index: 70; width: max-content;
            margin: 0 auto 8px; padding: 6px 12px; border-radius: 14px;
            border: 1px solid #287f7a; color: #bdf7ec;
            background: rgba(20,63,62,0.92); font-size: 10px; font-weight: bold;
        }
        
        .link-name { font-size: 13px; font-weight: bold; margin-bottom: 3px; color: var(--text-light);}
        .link-parts { font-size: 10px; color: #bbb; display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.25); padding: 4px 6px; border-radius: 4px; cursor: pointer; transition: 0.2s;}
        .link-parts:hover { background: rgba(0,0,0,0.45); color: #fff;}
        .link-parts-list { max-height: 0; overflow: hidden; transition: max-height 0.35s cubic-bezier(0, 1, 0.5, 1); font-size: 10px; color: #aaa; text-align: left; background: rgba(0,0,0,0.3); border-radius: 4px; margin-top: 2px;}
        .link-parts-list div { padding: 3px 6px; border-bottom: 1px solid rgba(255,255,255,0.05); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
        .link-parts-list div:last-child { border-bottom: none; }
        .link-box.expanded .link-parts-list { max-height: 250px; overflow-y: auto; padding: 2px 0;}
        .link-part-row {
            display: flex; align-items: center; gap: 6px;
        }
        .link-part-row .link-part-name {
            flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        }
        .link-part-remove {
            flex: 0 0 22px; width: 22px; height: 22px; border: 0;
            background: transparent; color: #9ca3a8; padding: 0; font-size: 16px;
            font-family: "Segoe UI Symbol", "Noto Sans Symbols", sans-serif;
            line-height: 22px; text-align: center; cursor: pointer; opacity: 0.58;
            transition: color 0.15s, opacity 0.15s, transform 0.15s;
        }
        .link-part-remove:hover,
        .link-part-remove:focus-visible {
            color: #ff7676; opacity: 1; transform: scale(1.08);
            filter: drop-shadow(0 0 3px rgba(255,86,86,0.32));
            outline: none;
        }
        .parts-list .link-part-row {
            padding: 5px 0; border-bottom: 1px solid rgba(255,255,255,0.08);
        }
        .expand-icon { transition: transform 0.3s; font-size: 8px;}
        .link-box.expanded .expand-icon { transform: rotate(180deg); }
        
        /* Right Panel List Item */
        .list-link-item {
            background: var(--bg-card); border: 1px solid #444; border-left: 5px solid var(--accent-blue);
            border-radius: 4px; padding: 10px; margin-bottom: 10px; cursor: grab;
            transition: all 0.2s; position: relative;
        }
        .list-link-item:hover { border-color: var(--accent-blue); box-shadow: 0 2px 8px rgba(0,0,0,0.4);}
        .list-link-item.finalized { border-color: var(--accent-green); border-left-color: var(--accent-green); background: #1b3320; }
        .list-link-item.selected {
            border-color: #00aaff !important; border-left-color: #00aaff !important;
            box-shadow: 0 0 14px rgba(0,170,255,0.55);
        }
        .list-link-item:active { cursor: grabbing; }
        
        .list-link-title { font-weight: bold; font-size: 13px; color: #fff; margin-bottom: 4px; display: flex; justify-content: space-between; align-items: center;}
        .list-link-title-left { display: flex; align-items: center; gap: 6px; }
        .link-color-dot {
            display: inline-block; width: 10px; height: 10px; border-radius: 50%;
            border: 1px solid rgba(255,255,255,0.75);
            box-shadow: 0 0 5px rgba(0,0,0,0.5); flex: 0 0 auto;
        }
        .cb-finalize { transform: scale(1.2); cursor: pointer; }
        
        .list-link-badge { background: #444; padding: 2px 6px; border-radius: 10px; font-size: 10px; font-weight: bold;}
        .list-link-parts { font-size: 10px; color: #aaa; background: #111; padding: 5px; border-radius: 4px; max-height: 50px; overflow-y: auto;}
        
        /* Drag & Drop Common */
        .drag-over { outline: 2px dashed var(--accent-green) !important; outline-offset: -2px; background: #1e3a1f !important; box-shadow: 0 0 0 1px rgba(76,175,80,0.35) inset !important;}
        .material-drop-target,
        .patcher-node.material-drop-target .link-box {
            outline: 2px dashed #53cfff !important; outline-offset: -3px;
            background: #163947 !important;
            box-shadow: 0 0 0 2px rgba(83,207,255,0.2), 0 0 18px rgba(83,207,255,0.42) !important;
        }
        .material-drag-card {
            display: flex; align-items: center; gap: 8px; margin-top: 8px; padding: 9px 10px;
            border: 1px dashed #4fb8e5; border-radius: 6px; color: #e9f8ff;
            background: linear-gradient(135deg, #173b4b 0%, #24363e 100%);
            cursor: grab; user-select: none;
        }
        .material-drag-card:hover {
            border-color: #75d7ff; box-shadow: 0 0 0 2px rgba(83,207,255,0.12);
        }
        .material-drag-card:active { cursor: grabbing; }
        .material-drag-card.dragging { opacity: 0.55; }
        .material-drag-swatch {
            width: 16px; height: 16px; flex: 0 0 auto; border-radius: 4px;
            border: 1px solid rgba(255,255,255,0.72); box-shadow: 0 1px 4px rgba(0,0,0,0.42);
        }
        .material-drag-copy { min-width: 0; flex: 1; }
        .material-drag-copy strong,
        .material-drag-copy small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .material-drag-copy strong { font-size: 11px; }
        .material-drag-copy small { margin-top: 2px; color: #9bc7da; font-size: 9px; }
        .material-drag-grip { color: #76d9ff; font-size: 15px; letter-spacing: -2px; }
        body.is-dragging .link-box,
        body.is-dragging .list-link-item,
        body.is-dragging .drag-over {
            transition: none !important;
            transform: none !important;
            box-shadow: none !important;
        }
        
        /* Properties Panel Form */
        .form-group { margin-bottom: 12px; }
        .form-group label { display: block; font-size: 11px; color: #aaa; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 1px;}
        .form-control { width: 100%; box-sizing: border-box; background: #333; border: 1px solid #555; color: white; padding: 6px; border-radius: 4px; font-size: 13px;}
        .form-control:focus { outline: none; border-color: var(--accent-blue); }
        .physical-material-panel {
            margin-top: 12px; padding: 10px; border: 1px solid #48606c;
            border-radius: 6px; background: #202a30;
        }
        .physical-material-heading {
            display: flex; justify-content: space-between; align-items: center;
            gap: 8px; margin-bottom: 9px; color: #dff6ff; font-size: 12px;
        }
        .material-library-details {
            margin-top: 10px; padding: 0; overflow: hidden;
            border: 1px solid #526873; border-radius: 6px; background: #222c31;
            box-shadow: 0 3px 9px rgba(0,0,0,0.18);
        }
        .material-library-details > summary {
            display: flex; align-items: center; justify-content: space-between;
            gap: 8px; padding: 8px 9px; border: 0;
            border-radius: 5px; background: #29363d; color: #dff6ff;
            font-size: 12px; font-weight: bold; cursor: pointer; list-style: none;
            user-select: none;
        }
        .material-library-details > summary:hover { background: #30414a; }
        .material-library-details > summary::-webkit-details-marker { display: none; }
        .material-library-details > summary::after { content: '▼'; color: #91b6c7; font-size: 9px; }
        .material-library-details[open] {
            border-color: #4f8198; background: #20292e;
            box-shadow: 0 0 0 1px rgba(54,169,221,0.08), 0 6px 14px rgba(0,0,0,0.24);
        }
        .material-library-details[open] > summary {
            border-radius: 5px 5px 0 0; border-bottom: 1px solid #446675;
            background: linear-gradient(180deg, #304650 0%, #293b43 100%);
        }
        .material-library-details[open] > summary::after { transform: rotate(180deg); }
        .material-library-content {
            padding: 10px; background: linear-gradient(180deg, #222e34 0%, #20282d 100%);
            box-shadow: inset 0 5px 10px rgba(0,0,0,0.10);
        }
        .component-material-row {
            display: grid; grid-template-columns: minmax(0, 1fr) minmax(118px, 0.9fr) 22px;
            gap: 6px; align-items: center; padding: 6px 0;
            border-bottom: 1px solid rgba(255,255,255,0.07);
        }
        .component-material-row:last-child { border-bottom: 0; }
        .component-material-copy { min-width: 0; }
        .component-material-copy strong {
            display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
            color: #f1f5f9; font-size: 11px;
        }
        .component-material-copy small { display: block; color: #91a4ae; margin-top: 2px; }
        .physical-material-picker-trigger {
            display: flex; align-items: center; justify-content: space-between; gap: 6px;
            text-align: left; cursor: pointer; white-space: nowrap; overflow: hidden;
        }
        .physical-material-picker-trigger span:first-child {
            min-width: 0; overflow: hidden; text-overflow: ellipsis;
        }
        .physical-material-picker-trigger span:last-child { color: #9eb4be; font-size: 9px; }
        .physical-material-popover {
            position: fixed; z-index: 12000; min-width: 270px; max-width: 380px;
            padding: 7px; border: 1px solid #4f7283; border-radius: 7px;
            background: #252c30; box-shadow: 0 12px 30px rgba(0,0,0,0.58);
        }
        .physical-material-popover-search {
            position: sticky; top: 0; z-index: 2; width: 100%; box-sizing: border-box;
            padding: 8px 9px; border: 1px solid #3aa5d5; border-radius: 5px;
            background: #17242a; color: #f2fbff; font-size: 12px;
        }
        .physical-material-popover-search:focus {
            outline: none; box-shadow: 0 0 0 2px rgba(58,165,213,0.18);
        }
        .physical-material-popover-results {
            max-height: min(52vh, 430px); overflow-y: auto; margin-top: 6px;
        }
        .physical-material-popover-category {
            padding: 8px 7px 4px; color: #70d6ff; font-size: 10px; font-weight: 800;
        }
        .physical-material-popover-option {
            display: flex; width: 100%; box-sizing: border-box; align-items: center;
            justify-content: space-between; gap: 9px; padding: 7px 8px;
            border: 0; border-radius: 4px; background: transparent; color: #edf5f8;
            text-align: left; cursor: pointer; font-size: 11px;
        }
        .physical-material-popover-option:hover,
        .physical-material-popover-option.active { background: #176a93; color: #fff; }
        .physical-material-popover-option small { flex: 0 0 auto; color: #a9bec7; }
        .physical-material-popover-option.active small { color: #d8f3ff; }
        .physical-material-popover-empty { padding: 18px 8px; color: #91a4ad; text-align: center; font-size: 11px; }
        .material-library-grid {
            display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-top: 8px;
        }
        .material-library-grid label { margin: 0; }
        .material-library-actions { display: grid; grid-template-columns: repeat(3, 1fr); gap: 5px; margin-top: 8px; }
        .material-library-actions button { cursor: pointer; }
        
        .empty-state { text-align: center; color: #666; margin-top: 20px; font-style: italic; line-height: 1.5; font-size:13px;}
        .hint-box { background: rgba(0, 122, 204, 0.1); border-left: 3px solid var(--accent-blue); padding: 10px; font-size: 12px; line-height: 1.4; margin-bottom: 10px;}
        .hint-box.green { background: rgba(76, 175, 80, 0.1); border-left-color: var(--accent-green); }
        
        /* Global Settings */
        .global-settings { display: flex; flex-wrap: wrap; justify-content: flex-end; align-items: center; gap: 10px; position: relative; z-index: 2; }
        .global-settings label { font-size: 13px; display: flex; align-items: center; gap: 5px; cursor: pointer; background: #333; padding: 6px 10px; border-radius: 4px; border: 1px solid #555; transition: 0.3s;}
        .global-settings label:hover { background: #444; border-color: var(--accent-blue); }
        .global-settings label.checked-state { background: rgba(76, 175, 80, 0.2); border-color: var(--accent-green); color: #fff; box-shadow: 0 0 8px rgba(76, 175, 80, 0.4);}
        .global-settings > .btn,
        .global-settings > label {
            height: 38px; min-height: 38px; box-sizing: border-box;
        }
        .global-settings > .btn { padding-top: 0; padding-bottom: 0; }
        .global-settings > .header-icon-btn {
            width: 38px; min-width: 38px; padding: 0;
        }
        .global-settings > label { padding: 0 10px; }
        .global-settings select { height: 28px; box-sizing: border-box; }
        .export-action-group {
            display: inline-flex; flex: 0 0 auto; align-items: stretch; gap: 0; height: 38px;
        }
        .export-mode-control {
            display: inline-flex; align-items: center; gap: 6px; height: 38px;
            box-sizing: border-box; margin: 0; padding: 0 10px;
            color: #ddd; background: #333; border: 1px solid #555;
            border-radius: 4px 0 0 4px;
            position: relative; z-index: 3; pointer-events: auto;
        }
        .export-mode-control > label {
            display: inline; flex: 0 0 auto; margin: 0; padding: 0;
            color: #ddd; background: transparent; border: 0; border-radius: 0;
            font-size: 13px; cursor: default; letter-spacing: 0; text-transform: none;
        }
        .export-mode-control > label:hover {
            color: #ddd; background: transparent; border-color: transparent;
        }
        .export-mode-control > select {
            height: 28px; box-sizing: border-box; position: relative; z-index: 4;
            pointer-events: auto; touch-action: manipulation; cursor: pointer;
        }
        .export-action-group > .btn {
            height: 38px; box-sizing: border-box; margin: 0;
            border-radius: 0 4px 4px 0; position: relative; z-index: 3;
            pointer-events: auto; touch-action: manipulation;
        }
        @media (max-width: 1100px) {
            .header { padding: 10px 12px; }
            .header h2 { font-size: 16px; }
        }
        
        .world-box {
            border: 3px dashed var(--accent-green);
            border-radius: 8px;
            padding: 15px 30px;
            background: rgba(76, 175, 80, 0.1);
            color: #fff;
            font-size: 16px;
            font-weight: bold;
            position: relative;
            z-index: 10;
            display: flex;
            flex-direction: column;
            align-items: center;
            box-shadow: 0 0 15px rgba(76, 175, 80, 0.3);
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .world-joint-text {
            font-size: 12px;
            color: #81c784;
            margin-top: 8px;
            font-weight: bold;
            background: rgba(0, 0, 0, 0.5);
            padding: 3px 8px;
            border-radius: 4px;
            text-transform: none;
            letter-spacing: normal;
        }
        .viewer-status {
            position: absolute; left: 18px; bottom: 18px; z-index: 21;
            max-width: 420px; padding: 10px 12px; border-radius: 6px;
            background: rgba(0,0,0,0.72); color: #e5e7eb; font-size: 12px;
            border: 1px solid rgba(255,255,255,0.12);
        }
        .viewer-status.error { border-color: rgba(239,68,68,0.7); color: #fecaca; }
        .viewer-pick-status {
            position: absolute; left: 50%; bottom: 16px; transform: translateX(-50%);
            z-index: 30; display: none; padding: 8px 14px; border-radius: 18px;
            background: rgba(0,122,204,0.92); color: white; font-size: 12px;
            font-weight: bold; pointer-events: none; box-shadow: 0 4px 14px rgba(0,0,0,0.45);
        }
        .viewer-located {
            animation: viewerLocatedPulse 0.55s ease-in-out 3;
            border-color: #00aaff !important;
            box-shadow: 0 0 0 3px rgba(0,170,255,0.3), 0 0 22px rgba(0,170,255,0.8) !important;
        }
        .tree-find-selected {
            position: absolute; left: 18px; bottom: 18px; z-index: 180;
            display: none; max-width: min(420px, calc(100% - 42px));
            padding: 9px 14px; border: 1px solid #5cc8ff; border-radius: 20px;
            background: rgba(0,92,153,0.94); color: white; font-weight: bold;
            font-size: 12px; cursor: pointer; overflow: hidden; text-overflow: ellipsis;
            white-space: nowrap; box-shadow: 0 4px 16px rgba(0,0,0,0.5);
        }
        .tree-find-selected:hover { background: #007acc; }
        @keyframes selectedLinkPulse {
            0%, 100% { box-shadow: 0 0 0 2px rgba(0,170,255,0.22), 0 0 12px rgba(0,170,255,0.55); }
            50% { box-shadow: 0 0 0 5px rgba(0,170,255,0.38), 0 0 28px rgba(0,170,255,0.95); }
        }
        @keyframes viewerLocatedPulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.06); }
        }
        /* Modal CSS */
        .modal-overlay {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.8); z-index: 2000;
            display: none; align-items: center; justify-content: center;
        }
        .modal-content {
            background: #2d2d30; border: 1px solid #444; border-radius: 12px;
            padding: 30px; width: 450px; text-align: center;
            box-shadow: 0 20px 50px rgba(0,0,0,0.5);
        }
        .modal-title { font-size: 20px; font-weight: bold; color: var(--accent-orange); margin-bottom: 15px; }
        .modal-desc { font-size: 14px; color: #ccc; line-height: 1.6; margin-bottom: 25px; }
        .modal-btns { display: flex; gap: 15px; }
        .modal-btn { flex: 1; padding: 12px; border-radius: 6px; font-weight: bold; cursor: pointer; border: none; font-size: 14px; }
        .modal-btn-primary { background: var(--accent-orange); color: white; }
        .modal-btn-secondary { background: #444; color: #ccc; }
        .standalone-import-content {
            width: min(620px, calc(100vw - 40px));
            max-height: calc(100vh - 40px);
            overflow-y: auto;
            text-align: left;
        }
        .standalone-import-content input[type="text"],
        .standalone-import-content input[type="file"] {
            width: 100%; box-sizing: border-box; margin-top: 6px; padding: 10px;
            color: #eee; background: #1f1f1f; border: 1px solid #555; border-radius: 5px;
        }
        .standalone-import-content input[type="file"] { min-height: 74px; }
        .workspace-manager-content select,
        .standalone-import-content select {
            width: 100%; box-sizing: border-box; margin-top: 6px; padding: 10px;
            color: #eee; background: #1f1f1f; border: 1px solid #555; border-radius: 5px;
        }
        .import-mode-tabs {
            display: grid; grid-template-columns: 1fr 1fr; gap: 8px;
            margin-bottom: 18px; padding: 4px; border-radius: 8px; background: #202023;
        }
        .import-mode-tab {
            padding: 11px 8px; border: 1px solid transparent; border-radius: 6px;
            color: #bbb; background: transparent; font-weight: bold; cursor: pointer;
        }
        .import-mode-tab.active {
            color: #fff; background: #356a85; border-color: #5ca0c2;
        }
        .standalone-import-status {
            display: none; margin-top: 12px; padding: 10px; border-radius: 5px;
            background: rgba(0,122,204,0.12); border-left: 3px solid var(--accent-blue);
            color: #ddd; font-size: 12px; line-height: 1.5;
        }
        .standalone-import-status.error {
            display: block; background: rgba(239,68,68,0.12); border-left-color: #ef4444; color: #fecaca;
        }
        .naming-assistant-preview {
            max-height: min(360px, 45vh); overflow: auto; margin-top: 12px;
            padding: 8px; border: 1px solid #49494d; border-radius: 6px; background: #202023;
        }
        .naming-assistant-row {
            display: grid; grid-template-columns: minmax(0, 1fr) 24px minmax(0, 1fr);
            gap: 8px; align-items: center; padding: 6px 7px;
            border-bottom: 1px solid rgba(255,255,255,0.06); font-size: 12px;
        }
        .naming-assistant-row:last-child { border-bottom: 0; }
        .naming-assistant-old { color: #aaa; overflow: hidden; text-overflow: ellipsis; }
        .naming-assistant-arrow { color: #666; text-align: center; }
        .naming-assistant-new { color: #8ed8ff; font-weight: bold; }

        .rename-wizard-overlay {
            position: absolute; bottom: 30px; left: 50%; transform: translateX(-50%);
            background: rgba(0,0,0,0.9); border: 2px solid var(--accent-orange);
            padding: 15px 25px; border-radius: 10px; z-index: 1000;
            display: none; align-items: center; gap: 20px;
            box-shadow: 0 0 20px rgba(217,119,6,0.3);
            animation: slideUp 0.4s ease;
        }
        @keyframes slideUp { from { transform: translate(-50%, 20px); opacity: 0; } to { transform: translate(-50%, 0); opacity: 1; } }
    </style>
</head>
<body>
    <div id="workspace-manager-modal" class="modal-overlay">
        <div class="modal-content standalone-import-content workspace-manager-content" style="width:min(520px, calc(100vw - 40px));">
            <div class="modal-title">다른 이름으로 저장·불러오기</div>
            <div class="modal-desc" style="text-align:left;margin-bottom:14px;">
                같은 조립품의 편집 상태를 이름별로 여러 개 저장할 수 있습니다.
                자동 저장은 별도로 계속 유지됩니다.
            </div>
            <div id="workspace-active-save" style="display:none;margin-bottom:16px;padding:12px;border:1px solid #496a7c;border-radius:7px;background:#202b31;">
                <div style="font-size:12px;color:#9fb3bd;">현재 이어서 작업 중</div>
                <div id="workspace-active-name" style="margin:5px 0 10px;color:#fff;font-weight:bold;"></div>
                <button id="workspace-continue-save-button" class="modal-btn"
                        style="width:100%;background:#356a85;color:#fff;"
                        onclick="saveCurrentNamedWorkspace()">현재 작업에 이어 저장</button>
            </div>
            <label style="font-size:12px;color:#aaa;">새 저장 작업 이름</label>
            <input id="workspace-save-name" type="text" placeholder="예: 카메라 장착 버전, 조인트 수정안 2"
                   autocomplete="off" onkeydown="if (event.key === 'Enter') saveNamedWorkspace()">
            <button class="modal-btn modal-btn-primary" style="width:100%;margin-top:10px;"
                    onclick="saveNamedWorkspace()">새 이름으로 저장</button>
            <label style="display:block;margin-top:18px;font-size:12px;color:#aaa;">저장된 작업 목록</label>
            <select id="workspace-saved-list" size="6"></select>
            <button class="modal-btn" style="width:100%;margin-top:10px;background:#356a85;color:#fff;"
                    onclick="reloadNamedWorkspace()">선택한 작업 불러오기</button>
            <div id="workspace-manager-status" class="standalone-import-status"></div>
            <div class="modal-btns" style="margin-top:16px;">
                <button class="modal-btn modal-btn-secondary" onclick="closeWorkspaceManager()">닫기</button>
            </div>
        </div>
    </div>

    <div id="naming-assistant-modal" class="modal-overlay">
        <div class="modal-content standalone-import-content" style="width:min(560px, calc(100vw - 40px));">
            <div class="modal-title">링크·조인트 이름 정렬</div>
            <div class="modal-desc" style="text-align:left;margin-bottom:10px;">
                WORLD 루트부터 부모→자식 배선 순서로
                <b>base_link, joint_1, link_1…</b> 형식으로 정리합니다.
                분기가 있으면 현재 자식 배선 순서를 따릅니다.
            </div>
            <div id="naming-assistant-summary" style="font-size:12px;color:#aaa;"></div>
            <div id="naming-assistant-preview" class="naming-assistant-preview"></div>
            <div class="modal-btns" style="margin-top:16px;">
                <button id="naming-assistant-apply" class="modal-btn"
                        style="background:#356a85;color:#fff;"
                        onclick="applyStructureNamingAssistant()">정리 후 URDF 생성</button>
                <button id="naming-assistant-keep" class="modal-btn modal-btn-secondary"
                        onclick="continueExportWithoutStructureRename()">현재 이름 유지하고 생성</button>
            </div>
        </div>
    </div>

    <div id="standalone-import-modal" class="modal-overlay">
        <div class="modal-content standalone-import-content">
            <div id="standalone-import-title" class="modal-title">불러오기</div>
            <div class="import-mode-tabs">
                <button id="import-mode-cad" class="import-mode-tab active"
                        onclick="setStandaloneImportMode('cad')">CAD 조립품 불러오기</button>
                <button id="import-mode-workspace" class="import-mode-tab"
                        onclick="setStandaloneImportMode('workspace')">이전 작업 불러오기</button>
            </div>
            <div id="standalone-cad-import-panel">
                <div id="standalone-reimport-note" class="modal-desc"
                     style="display:none;text-align:left;margin-bottom:12px;padding:10px;border:1px solid #397b58;border-radius:6px;background:#173125;color:#bfe8cc;">
                    수정된 STEP/CAD를 다시 선택하세요. 동일한 부품을 연결하여 현재 링크 그룹,
                    조인트, 이름과 바닥면 설정을 유지하고 형상·물성·CAD 위치만 갱신합니다.
                </div>
                <div class="modal-desc" style="text-align:left;">
                    <b>Inventor IAM</b>, SolidWorks·Creo·CATIA 등의 조립품 또는
                    STEP, BREP, IGES, STL 형상을 선택하세요.<br>
                    Inventor는 아래 직접 연결을 사용하면 <b>IPT를 하나씩 선택할 필요가 없습니다.</b><br>
                    다른 CAD는 <b>조립 구조를 유지한 STEP AP242/AP214/AP203</b>을 권장합니다.
                    부품 위치를 유지한 채 각각의 링크 후보로 분리합니다.
                </div>
                <label style="font-size:12px; color:#aaa;">프로젝트 이름</label>
                <input id="standalone-project-name" type="text" value="new_robot" autocomplete="off">
                <div id="standalone-inventor-direct" style="margin-top:16px; padding:12px; border:1px solid #4a6b8a; border-radius:7px; background:#17212b;">
                    <div id="standalone-inventor-direct-title" style="font-size:12px; color:#9ecfff; margin-bottom:10px;">
                        IPT를 따로 선택하지 않는 Inventor 직접 연결
                    </div>
                    <div class="modal-btns" style="margin:0; flex-wrap:wrap;">
                        <button class="modal-btn modal-btn-primary" style="flex:1 1 230px;"
                                onclick="importDirectInventor('/import/inventor-active')">
                            🔗 현재 열린 Inventor 조립품
                        </button>
                        <button class="modal-btn modal-btn-secondary" style="flex:1 1 230px;"
                                onclick="importDirectInventor('/import/inventor-file')">
                            📁 원본 IAM 경로 선택
                        </button>
                    </div>
                </div>
                <div style="margin:15px 0 6px; text-align:center; color:#777; font-size:12px;">— 또는 파일 업로드 —</div>
                <label style="display:block; margin-top:14px; font-size:12px; color:#aaa;">조립품·형상 파일</label>
                <input id="standalone-files" type="file" multiple
                       accept=".iam,.ipt,.sldasm,.sldprt,.asm,.prt,.catproduct,.catpart,.3dxml,.jt,.par,.psm,.x_t,.x_b,.sat,.sab,.stl,.step,.stp,.brep,.iges,.igs,.petasos.json">
                <label style="display:block; margin-top:14px; font-size:12px; color:#aaa;">또는 조립품 프로젝트 폴더</label>
                <input id="standalone-folder" type="file" multiple webkitdirectory directory>
                <div class="modal-desc" style="text-align:left; margin-top:12px; font-size:12px;">
                    파일 업로드는 직접 연결을 사용할 수 없을 때의 대체 방법입니다.
                    이 경우 참조 부품이 있는 프로젝트 폴더 전체를 함께 선택하세요.
                </div>
                <div id="standalone-import-status" class="standalone-import-status"></div>
                <div class="modal-btns" style="margin-top:18px;">
                    <button id="standalone-import-submit" class="modal-btn modal-btn-primary" onclick="importStandaloneAssembly()">가져오기</button>
                    <button class="modal-btn modal-btn-secondary" onclick="closeStandaloneImport()">취소</button>
                </div>
            </div>
            <div id="standalone-workspace-load-panel" style="display:none;">
                <div class="modal-desc" style="text-align:left;margin-bottom:14px;">
                    조립품별로 이름을 붙여 저장했던 프리뷰 편집 작업을 선택하세요.
                    링크 그룹, 조인트, 바닥면과 뷰어 설정까지 저장 당시 상태로 불러옵니다.
                </div>
                <label style="font-size:12px;color:#aaa;">저장된 이전 작업</label>
                <select id="standalone-workspace-list" size="9"></select>
                <div id="standalone-workspace-status" class="standalone-import-status"></div>
                <div class="modal-btns" style="margin-top:18px;">
                    <button class="modal-btn" style="background:#356a85;color:#fff;"
                            onclick="loadStandaloneWorkspace()">선택한 작업 불러오기</button>
                    <button class="modal-btn modal-btn-secondary" onclick="closeStandaloneImport()">취소</button>
                </div>
            </div>
        </div>
    </div>

    <div id="modal-container" class="modal-overlay">
        <div class="modal-content">
            <div class="modal-title">⚠️ 조인트 정렬 확인</div>
            <div class="modal-desc">
                로봇 구조가 변경되어 조인트 이름이 순서대로 정렬되지 않았습니다.<br>
                <b>joint_1, joint_2...</b> 와 같이 순서대로 정리하시겠습니까?
            </div>
            <div class="modal-btns">
                <button class="modal-btn modal-btn-primary" onclick="startRenameWizard()">✅ 네, 정리할게요</button>
                <button class="modal-btn modal-btn-secondary" onclick="proceedSave()">아니오, 그냥 저장</button>
            </div>
        </div>
    </div>

    <div id="rename-wizard" class="rename-wizard-overlay">
        <div style="color:#fff;">
            <div id="wizard-joint-name" style="font-size:16px; font-weight:bold; color:var(--accent-orange);">joint_1</div>
            <div style="font-size:12px; color:#aaa;">이 조인트의 이름을 추천대로 변경하시겠습니까?</div>
        </div>
        <div style="display:flex; gap:10px;">
            <button class="btn" style="background:var(--accent-orange);" onclick="applyWizardRename()">✅ 네, 변경</button>
            <button class="btn" style="background:#444;" onclick="nextWizardStep()">⏩ 건너뛰기</button>
            <button class="btn" style="background:#d32f2f;" onclick="closeRenameWizard()">❌ 중단</button>
        </div>
    </div>
    <input type="checkbox" id="fix-to-world" checked style="display:none;">
    <input type="hidden" id="root-joint-mode" value="world">
    <div class="header">
        <h2>URDF 구조 병합 및 3D 프리뷰 에디터</h2>
        <div class="global-settings">
            <div class="language-switcher" role="group" aria-label="Language / 언어" data-no-i18n>
                <button id="language-en" type="button" onclick="setPetasosLanguage('en')">ENGLISH</button>
                <button id="language-ko" type="button" onclick="setPetasosLanguage('ko')">한국어</button>
            </div>
            <button id="standalone-import-button" class="btn header-icon-btn"
                    style="display:none;" onclick="openStandaloneImport()"
                    title="조립품 불러오기" aria-label="조립품 불러오기">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M3.5 6.5h6l2 2h9v9.5h-17z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>
                    <path d="M3.5 9h17" fill="none" stroke="currentColor" stroke-width="1.7"/>
                </svg>
            </button>
            <button id="standalone-reimport-button" class="btn header-icon-btn"
                    style="display:none;" onclick="openStandaloneReimport()"
                    title="CAD 업데이트 · 기존 편집 유지" aria-label="CAD 업데이트 · 기존 편집 유지">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M19 8a7 7 0 10.5 7.8" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>
                    <path d="M15.5 4.5H19V8M19.5 15.5H16V19" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            </button>
            <div class="header-workspace-switcher">
                <button id="header-workspace-name" class="header-workspace-name"
                        type="button" onclick="toggleHeaderWorkspaceMenu(event)"
                        title="현재 작업 · 클릭하여 저장 작업 전환"
                        aria-label="현재 작업 선택" aria-expanded="false"
                        aria-controls="header-workspace-menu">
                    <span class="header-workspace-label">현재 작업</span>
                    <strong id="header-workspace-value" class="header-workspace-value">새 작업</strong>
                    <svg class="header-workspace-chevron" viewBox="0 0 10 6" aria-hidden="true">
                        <path d="M1 1l4 4 4-4" fill="none" stroke="currentColor"
                              stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                </button>
                <div id="header-workspace-menu" class="header-workspace-menu"
                     role="menu" aria-label="저장된 작업">
                    <div class="header-workspace-menu-status">저장된 작업을 읽는 중...</div>
                </div>
            </div>
            <button id="workspace-save-button" class="btn header-icon-btn"
                    style="display:none;"
                    onclick="saveActiveWorkspaceFromHeader()"
                    title="저장" aria-label="현재 작업 저장">
                <svg class="save-default-icon" viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M5 3.5h12l2 2V20.5H5z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>
                    <path d="M8 3.5v6h8v-6M8 20.5v-7h8v7" fill="none" stroke="currentColor" stroke-width="1.7"/>
                </svg>
                <svg class="save-complete-icon" viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M5 12.5l4.2 4.2L19 7" fill="none" stroke="currentColor"
                          stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            </button>
            <button id="workspace-save-as-button" class="btn header-icon-btn"
                    style="display:none;"
                    onclick="openWorkspaceManager('save_as')"
                    title="다른 이름으로 저장·불러오기" aria-label="다른 이름으로 저장·불러오기">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M4.5 3.5h11l2 2v7.2M4.5 3.5v17h8" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>
                    <path d="M7.5 3.5v6h7v-6M7.5 20.5v-7h6" fill="none" stroke="currentColor" stroke-width="1.7"/>
                    <path d="M13.4 18.8l5.7-5.7 1.8 1.8-5.7 5.7-2.5.7z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
                </svg>
            </button>
            <div class="export-action-group">
                <div class="export-mode-control"
                     title="URDF만 필요하면 기본 패키지, MoveIt 설정·검사까지 필요하면 export/ros_ws 작업공간을 선택하세요.">
                    <label for="export-mode">📦 출력 유형</label>
                    <select id="export-mode" onchange="scheduleWorkspaceAutosave()"
                            aria-label="출력 유형"
                            style="background:#252525; color:#fff; border:1px solid #666; border-radius:4px; padding:5px 8px;">
                        <option value="description" selected>ROS 2 기본 패키지</option>
                        <option value="moveit">MoveIt export/ros_ws + WSL 검사</option>
                    </select>
                </div>
                <button type="button" class="btn btn-green" onclick="saveAndExit()">URDF 생성</button>
            </div>
        </div>
    </div>
    
    <div class="main-content">
        <div class="left-pane">
            <!-- 3D 뷰어 -->
            <div class="preview-pane">
                <div class="preview-overlay">로봇 3D 뷰어</div>
                <div class="preview-hint">좌클릭: 선택 · Ctrl+좌클릭: 다중 선택 · 더블클릭: 부품만 보기 · 우클릭/휠클릭 드래그: 카메라 이동 · 휠: 확대/축소</div>
                <div class="preview-controls">
                    <section id="ground-origin-panel" class="ground-origin-panel">
                        <div class="ground-origin-heading">
                            <strong>원점 좌표 설정</strong>
                            <span id="ground-origin-state" class="ground-origin-state">필수 설정</span>
                        </div>
                        <button id="ground-face-button" class="ground-face-btn primary" onclick="toggleGroundFacePick()">바닥면·원점 지정</button>
                        <div id="ground-face-help" class="ground-face-help">로봇의 바닥면을 선택하여 월드 XYZ 원점을 확정합니다.</div>
                        <div class="ground-origin-secondary">
                            <label class="ground-origin-axis-label" for="preview-up-axis">모델 위쪽 축
                                <select id="preview-up-axis" class="preview-axis-select" onchange="setPreviewUpAxis(this.value)">
                                    <option value="y">Y-up · Inventor</option>
                                    <option value="z">Z-up · Fusion/ROS</option>
                                    <option value="x">X-up</option>
                                </select>
                            </label>
                            <button class="ground-face-btn ground-origin-reset" onclick="resetGroundFace()">자동축 복원</button>
                        </div>
                        <label class="ground-edge-toggle" for="ground-align-edge"
                               title="바닥면의 긴 모서리를 기준으로 모델의 수평 방향까지 자동 정렬합니다.">
                            <input id="ground-align-edge" type="checkbox" checked>
                            <span class="ground-edge-toggle-copy">
                                <strong>바닥면 방향도 자동 정렬</strong>
                                <small>긴 모서리를 월드 X/Z축에 맞춤</small>
                            </span>
                        </label>
                        <div id="ground-origin-offset" class="ground-origin-offset">
                            <div class="ground-origin-offset-title">
                                <span>모델 위치 보정</span>
                                <small>ROS XYZ · mm</small>
                            </div>
                            <div class="ground-origin-offset-fields">
                                <label>X
                                    <input id="ground-offset-x" type="number" step="1" value="0"
                                           onchange="setGroundOriginOffset('x', this.value)">
                                </label>
                                <label>Y
                                    <input id="ground-offset-y" type="number" step="1" value="0"
                                           onchange="setGroundOriginOffset('y', this.value)">
                                </label>
                                <label>Z
                                    <input id="ground-offset-z" type="number" step="1" value="0"
                                           onchange="setGroundOriginOffset('z', this.value)">
                                </label>
                            </div>
                        </div>
                    </section>
                    <h3>보기 설정</h3>
                    <label class="preview-control-row"><input type="checkbox" checked onchange="toggleVisualMeshes(this.checked)"> Show Visual</label>
                    <label class="preview-control-row"><input type="checkbox" onchange="toggleCollisionMeshes(this.checked)"> Show Collision</label>
                    <label class="preview-control-row"><input type="checkbox" onchange="toggleInertiaMarkers(this.checked)"> Show Inertia</label>
                    <label class="preview-control-row"><input type="checkbox" checked onchange="toggleWorldFrame(this.checked)"> Show World Frame</label>
                    <label class="preview-control-row"><input type="checkbox" id="show-joint-frames" onchange="toggleJointFrames(this.checked)"> Show Joint Frames</label>
                    <div class="preview-control-range">
                        <label>Joint Frame Size</label>
                        <input type="range" id="joint-frame-size" min="20" max="500" value="120" oninput="resizeJointFrames(this.value)">
                    </div>
                    <label class="preview-control-row"><input type="checkbox" onchange="toggleLinkFrames(this.checked)"> Show Link Frames</label>
                    <div class="preview-control-range">
                        <label>Link Frame Size</label>
                        <input type="range" min="20" max="500" value="120" oninput="resizeLinkFrames(this.value)">
                    </div>
                    <div class="preview-subhead"><span>Joints</span></div>
                    <div class="preview-actions">
                        <button class="mini-btn" onclick="randomizePreviewJoints()">Randomize</button>
                        <button class="mini-btn" onclick="resetPreviewJoints()">Reset</button>
                    </div>
                    <div id="joint-controls"></div>
                </div>
                <div class="viewer-status" id="viewer-status">3D mesh loading...</div>
                <div class="viewer-pick-status" id="viewer-pick-status"></div>
                <div id="viewer-3d-container"></div>
                <div id="viewer-context-menu" class="viewer-context-menu">
                    <div id="viewer-context-title" class="viewer-context-title">선택한 부품</div>
                    <button id="viewer-context-group" type="button"
                            onclick="groupViewerSelectedComponents()">선택 부품의 링크를 하나로 그룹화</button>
                </div>
            </div>
            <div class="resizer-h" title="드래그해서 뷰어와 트리 높이 조절"></div>
            <!-- 트리 뷰 -->
            <div class="viz-pane" id="viz-pane">
                <div class="preview-overlay tree-title-overlay" style="color: #fff; z-index: 100;">로봇 구조 트리</div>
                <div class="tree" id="tree"></div>
            </div>
            <button id="tree-find-selected" class="tree-find-selected"
                    onclick="findSelectedLinkInTree()">🎯 선택 링크 다시 찾기</button>
        </div>
        
        <!-- 우측 속성/리스트 -->
        <div class="resizer-v" title="드래그해서 오른쪽 패널 폭 조절"></div>
        <div class="edit-pane">
            <div id="selected-properties-header" class="pane-section-header">선택된 항목 속성</div>
            <div class="pane-body" id="panel-body">
                <div class="hint-box">
                    💡 항목을 클릭하면 3D 뷰어에서 해당 부품이 <span style="color:#007acc; font-weight:bold;">파란색</span>으로 강조됩니다.
                </div>
            </div>
            <div class="pane-section-divider" aria-hidden="true"></div>
            <div class="pane-section-header">
                링크 리스트
                <span id="link-count-badge" style="font-weight:normal; font-size:12px; color:#aaa;"></span>
            </div>
            <div class="pane-grouping">
                <div id="grouping-list"></div>
                <div class="pane-grouping-help">링크 카드를 드래그하여 다른 링크에 부품을 합칠 수 있습니다.</div>
            </div>
        </div>
    </div>

    <script>
        const PETASOS_LANGUAGE_KEY = 'petasos.ui.language';
        let petasosLanguage = 'ko';
        let petasosApplyingLanguage = false;
        const petasosTextOriginals = new WeakMap();
        const petasosAttributeOriginals = new WeakMap();
        const PETASOS_TRANSLATED_ATTRIBUTES = ['title', 'aria-label', 'placeholder'];

        const PETASOS_ENGLISH = Object.freeze({
            '클릭하여 링크 및 조인트 비활성화 (3D 모델 숨김)': 'Click to deactivate link and joint (hide 3D model)',
            '클릭하여 링크 및 조인트 활성화 (3D 모델 표시)': 'Click to activate link and joint (show 3D model)',
            '활성화 상태 (클릭하여 비활성화 및 3D 모델 숨김)': 'Active state (Click to deactivate and hide 3D model)',
            '비활성화 상태 (클릭하여 활성화 및 3D 모델 표시)': 'Deactivated state (Click to activate and show 3D model)',
            '링크 비활성화됨 (클릭 시 활성화 및 3D 모델 표시)': 'Link Deactivated (Click to activate and show 3D model)',
            '링크 활성화 중 (클릭 시 비활성화 및 3D 모델 숨김)': 'Link Active (Click to deactivate and hide 3D model)',
            '조인트 비활성화됨 (클릭 시 활성화 및 3D 모델 표시)': 'Joint Deactivated (Click to activate and show 3D model)',
            '조인트 활성화 중 (클릭 시 비활성화 및 3D 모델 숨김)': 'Joint Active (Click to deactivate and hide 3D model)',
            '비활성': 'DISABLED',
            '다른 이름으로 저장·불러오기': 'Save As / Load',
            '같은 조립품의 편집 상태를 이름별로 여러 개 저장할 수 있습니다. 자동 저장은 별도로 계속 유지됩니다.': 'Save multiple named editing states for the same assembly. Autosave continues separately.',
            '현재 이어서 작업 중': 'Currently continuing',
            '현재 작업에 이어 저장': 'Save to current work',
            '새 저장 작업 이름': 'New saved-work name',
            '예: 카메라 장착 버전, 조인트 수정안 2': 'e.g. Camera mount version, joint revision 2',
            '새 이름으로 저장': 'Save with a new name',
            '저장된 작업 목록': 'Saved work',
            '선택한 작업 불러오기': 'Load selected work',
            '닫기': 'Close',
            '링크·조인트 이름 정렬': 'Order link and joint names',
            'WORLD 루트부터 부모→자식 배선 순서로': 'Starting at the WORLD root, follows parent-to-child connections',
            '형식으로 정리합니다. 분기가 있으면 현재 자식 배선 순서를 따릅니다.': 'and renames items in this format. Branches follow the current child connection order.',
            '정리 후 URDF 생성': 'Rename and generate URDF',
            '현재 이름 유지하고 생성': 'Keep current names and generate',
            '불러오기': 'Import',
            'CAD 조립품 불러오기': 'Import CAD assembly',
            '이전 작업 불러오기': 'Load previous work',
            ', SolidWorks·Creo·CATIA 등의 조립품 또는 STEP, BREP, IGES, STL 형상을 선택하세요.': ', a SolidWorks, Creo, or CATIA assembly, or STEP, BREP, IGES, or STL geometry.',
            '등의 조립품 또는': 'assembly, or',
            '형상을 선택하세요.': 'geometry.',
            'Inventor는 아래 직접 연결을 사용하면': 'With the direct Inventor connection below,',
            'IPT를 하나씩 선택할 필요가 없습니다.': 'you do not need to select IPT files individually.',
            '다른 CAD는': 'For other CAD systems,',
            '조립 구조를 유지한 STEP AP242/AP214/AP203': 'STEP AP242/AP214/AP203 that preserves the assembly structure ',
            '을 권장합니다. 부품 위치를 유지한 채 각각의 링크 후보로 분리합니다.': 'is recommended. Parts retain their positions and are separated into link candidates.',
            '프로젝트 이름': 'Project name',
            'IPT를 따로 선택하지 않는 Inventor 직접 연결': 'Direct Inventor connection without selecting IPT files',
            '🔗 현재 열린 Inventor 조립품': '🔗 Currently open Inventor assembly',
            '📁 원본 IAM 경로 선택': '📁 Select original IAM path',
            '— 또는 파일 업로드 —': '— or upload files —',
            '조립품·형상 파일': 'Assembly / geometry files',
            '또는 조립품 프로젝트 폴더': 'Or assembly project folder',
            '파일 업로드는 직접 연결을 사용할 수 없을 때의 대체 방법입니다. 이 경우 참조 부품이 있는 프로젝트 폴더 전체를 함께 선택하세요.': 'File upload is a fallback when direct connection is unavailable. Select the entire project folder containing all referenced parts.',
            '가져오기': 'Import',
            '취소': 'Cancel',
            '조립품별로 이름을 붙여 저장했던 프리뷰 편집 작업을 선택하세요. 링크 그룹, 조인트, 바닥면과 뷰어 설정까지 저장 당시 상태로 불러옵니다.': 'Select a named preview editing session saved for an assembly. Link groups, joints, ground plane, and viewer settings are restored.',
            '저장된 이전 작업': 'Saved previous work',
            '⚠️ 조인트 정렬 확인': '⚠️ Confirm joint ordering',
            '로봇 구조가 변경되어 조인트 이름이 순서대로 정렬되지 않았습니다.': 'The robot structure changed, so joint names are no longer sequential.',
            '와 같이 순서대로 정리하시겠습니까?': 'in sequence?',
            '✅ 네, 정리할게요': '✅ Yes, reorder',
            '아니오, 그냥 저장': 'No, save as is',
            '이 조인트의 이름을 추천대로 변경하시겠습니까?': 'Rename this joint as recommended?',
            '✅ 네, 변경': '✅ Yes, rename',
            '⏩ 건너뛰기': '⏩ Skip',
            '❌ 중단': '❌ Stop',
            'URDF 구조 병합 및 3D 프리뷰 에디터': 'URDF Structure Merge & 3D Preview Editor',
            '조립품 불러오기': 'Import assembly',
            'CAD 업데이트 · 기존 편집 유지': 'Update CAD · keep current edits',
            'CAD 업데이트': 'Update CAD',
            '수정된 STEP/CAD를 다시 선택하세요. 동일한 부품을 연결하여 현재 링크 그룹, 조인트, 이름과 바닥면 설정을 유지하고 형상·물성·CAD 위치만 갱신합니다.': 'Select the updated STEP/CAD file again. Matching parts keep the current link groups, joints, names, and ground settings while geometry, physical properties, and CAD poses are refreshed.',
            '업데이트 적용': 'Apply update',
            '현재 작업 · 클릭하여 저장 작업 전환': 'Current work · Click to switch saved work',
            '현재 작업 선택': 'Select current work',
            '현재 작업': 'Current work',
            '새 작업': 'New work',
            '저장된 작업': 'Saved work',
            '저장된 작업을 읽는 중...': 'Loading saved work...',
            '저장': 'Save',
            '현재 작업 저장': 'Save current work',
            '저장 · 현재 조립품 작업': 'Save · Current assembly work',
            'URDF만 필요하면 기본 패키지, MoveIt 설정·검사까지 필요하면 export/ros_ws 작업공간을 선택하세요.': 'Choose the basic package for URDF only, or the export/ros_ws workspace for MoveIt setup and validation.',
            '📦 출력 유형': '📦 Output type',
            '출력 유형': 'Output type',
            'ROS 2 기본 패키지': 'Basic ROS 2 package',
            'MoveIt export/ros_ws + WSL 검사': 'MoveIt export/ros_ws + WSL validation',
            'URDF 생성': 'Generate URDF',
            '로봇 3D 뷰어': 'Robot 3D Viewer',
            '좌클릭: 선택 · Ctrl+좌클릭: 다중 선택 · 더블클릭: 부품만 보기 · 우클릭/휠클릭 드래그: 카메라 이동 · 휠: 확대/축소': 'Left-click: select · Ctrl+left-click: multi-select · Double-click: isolate part · Right/middle drag: move camera · Wheel: zoom',
            '원점 좌표 설정': 'Origin coordinates',
            '필수 설정': 'Required',
            '바닥면·원점 지정': 'Set ground plane & origin',
            '로봇의 바닥면을 선택하여 월드 XYZ 원점을 확정합니다.': 'Select the robot ground plane to set the world XYZ origin.',
            '모델 위쪽 축': 'Model up axis',
            '자동축 복원': 'Restore automatic axis',
            '바닥면의 긴 모서리를 기준으로 모델의 수평 방향까지 자동 정렬합니다.': 'Automatically aligns the model horizontally using the longest ground-plane edge.',
            '바닥면 방향도 자동 정렬': 'Auto-align ground-plane direction',
            '긴 모서리를 월드 X/Z축에 맞춤': 'Align longest edge to world X/Z axis',
            '모델 위치 보정': 'Model position offset',
            'ROS XYZ · mm': 'ROS XYZ · mm',
            '보기 설정': 'View settings',
            '선택한 부품': 'Selected parts',
            '선택 부품의 링크를 하나로 그룹화': 'Group selected parts into one link',
            '드래그해서 뷰어와 트리 높이 조절': 'Drag to resize viewer and tree',
            '로봇 구조 트리': 'Robot Structure Tree',
            '🎯 선택 링크 다시 찾기': '🎯 Find selected link',
            '드래그해서 오른쪽 패널 폭 조절': 'Drag to resize right panel',
            '선택된 항목 속성': 'Selected Item Properties',
            '💡 항목을 클릭하면 3D 뷰어에서 해당 부품이': '💡 Click an item to highlight that part in',
            '파란색': 'blue ',
            '으로 강조됩니다.': 'in the 3D viewer.',
            '링크 리스트': 'Link List',
            '링크 카드를 드래그하여 다른 링크에 부품을 합칠 수 있습니다.': 'Drag a link card onto another to merge its parts.',
            '설정 완료': 'Complete',
            '✕ 지정 취소': '✕ Cancel selection',
            '변경': 'Change',
            '세부 설정 접기': 'Collapse details',
            '세부 설정 펼치기': 'Expand details',
            '연속 회전 · 최소/최대 제한 없음': 'Continuous rotation · no minimum/maximum limit',
            '미리보기 조작 범위 · URDF 회전 제한 아님': 'Preview control range · not a URDF rotation limit',
            '미지정': 'Not set',
            '최소°': 'Minimum°',
            '최대°': 'Maximum°',
            '정밀 CAD 후보 없음 — 메쉬 추정 사용': 'No precise CAD candidate — using mesh estimate',
            '정밀 CAD 자석에 붙었습니다.': 'Snapped to a precise CAD feature.',
            '✕ 조인트 위치 지정 취소': '✕ Cancel joint placement',
            '🎯 3D에서 조인트 중심·축 다시 찍기': '🎯 Pick joint center & axis again in 3D',
            '1/2 부모 연결점': '1/2 Parent connection point',
            '2/2 자식 연결점': '2/2 Child connection point',
            '바닥면 지정 대기': 'Waiting for ground-plane selection',
            '이미 같은 링크에 포함된 부품입니다': 'Parts are already in the same link',
            '💡 구조가 변경되었습니다!': '💡 Structure changed!',
            '조인트 이름을 순서대로(joint_1...) 자동 재정렬하시겠습니까?': 'Automatically reorder joint names (joint_1...)?',
            '네, 정리할게요': 'Yes, reorder',
            '아니오': 'No',
            '링크': 'Link',
            '미연결 링크': 'Unconnected link',
            '조인트': 'Joint',
            '이 이름으로 정렬': 'Apply this naming order',
            '중복된 조인트 이름은 URDF에서 사용할 수 있어 먼저 정리해야 합니다.': 'Duplicate joint names cannot be used in URDF and must be resolved first.',
            '중복 이름이 있어 현재 이름 사용 불가': 'Current names unavailable because duplicates exist',
            '▦ 자동 정렬': '▦ Auto layout',
            '↕ 이름 정렬': '↕ Order names',
            '⊙ 전체 보기': '⊙ Fit all',
            '▣ 그룹화': '▣ Group',
            '선택 병합': 'Merge selected',
            '그룹 해제': 'Ungroup',
            '✂ 선택 배선 끊기': '✂ Disconnect selected',
            '로봇 팔처럼 바닥에 고정된 모델일 경우 체크하세요. 모바일 로봇이면 해제합니다.': 'Enable for floor-mounted models such as robot arms; disable for mobile robots.',
            'world_joint 생성': 'Create world_joint',
            'base_footprint_joint 생성': 'Create base_footprint_joint',
            '루트 조인트 없음': 'No root joint',
            '◎ BASE FOOTPRINT 위치 지정': '◎ Set BASE FOOTPRINT position',
            '◎ BASE FOOTPRINT 위치 재설정': '◎ Reset BASE FOOTPRINT position',
            'BASE FOOTPRINT 설정': 'BASE FOOTPRINT settings',
            '위치 선택 중': 'Selecting position',
            '위치 필요': 'Position required',
            '✕ 위치 지정 취소': '✕ Cancel position selection',
            '◎ 위치 다시 선택': '◎ Select position again',
            '◎ 3D에서 위치 선택': '◎ Select position in 3D',
            '기준 좌표는 유지하고 BASE FOOTPRINT 위치만 별도로 설정합니다.': 'Keeps the reference coordinates and configures only the BASE FOOTPRINT position.',
            '위치 지정 완료': 'Position set',
            '위치 미지정': 'Position not set',
            '루트를 직접 연결하세요': 'Connect the root link',
            '기준 프레임 연결 없음': 'No reference-frame connection',
            '루트 링크를 WORLD 또는 BASE FOOTPRINT 기준 프레임에 연결합니다.': 'Connect the root link to the WORLD or BASE FOOTPRINT reference frame.',
            '루트를 직접 연결하세요': 'Connect the root manually',
            '루트 선택 가능 · 바닥 고정 꺼짐': 'Root selectable · ground fixation off',
            'WORLD 출력 포트': 'WORLD output port',
            '더블클릭하면 WORLD 배선을 끊습니다': 'Double-click to disconnect WORLD',
            'WORLD에서 루트 링크 연결을 시작합니다': 'Start connecting the root link from WORLD',
            '분리': 'Separate',
            '묶인 부품을 각각의 카드로 그룹 해제': 'Ungroup bundled parts into individual cards',
            '묶음 후보': 'Grouping candidate',
            '미연결': 'Unconnected',
            '더블클릭하면 이 배선을 끊습니다': 'Double-click to disconnect this connection',
            '부모 링크의 출력 포트를 연결하세요': 'Connect the parent link output port',
            '새 자식 링크를 연결합니다': 'Connect a new child link',
            '더블클릭하여 링크 이름 수정': 'Double-click to rename link',
            '링크 이름 수정': 'Rename link',
            '링크가 하나뿐입니다. 조립품을 불러오면 이곳에 링크 노드가 표시됩니다.': 'There is only one link. Import an assembly to display link nodes here.',
            '✕ 그룹화 취소': '✕ Cancel grouping',
            'fixed 조인트': 'fixed joint',
            '움직이지 않는 고정 연결이므로 축·리밋·effort·velocity 설정이 필요하지 않습니다.': 'This is a rigid connection, so axis, limits, effort, and velocity settings are unnecessary.',
            'URDF 동작 설정': 'URDF motion settings',
            '최소 이동 (m)': 'Minimum travel (m)',
            '최대 이동 (m)': 'Maximum travel (m)',
            '연속 회전이므로 lower/upper를 URDF에 출력하지 않습니다.': 'Continuous joints do not output lower/upper limits in URDF.',
            '최대 힘': 'Maximum effort',
            '최대 속도': 'Maximum velocity',
            '왼쪽 구조 트리나 아래 리스트에서 항목을 클릭하여 상세 속성을 편집하세요.': 'Click an item in the structure tree or list to edit its properties.',
            '왼쪽 구조 트리나 아래 리스트에서 항목을 클릭하여': 'Click an item in the structure tree or list to',
            '상세 속성을 편집하세요.': 'edit its properties.',
            '✅ URDF 공식 링크로 확정됨': '✅ Confirmed as an official URDF link',
            '⚠️ 아직 그룹화/확정되지 않은 부품': '⚠️ Part not yet grouped/confirmed',
            '대표 링크 이름 (URDF)': 'Primary link name (URDF)',
            '↗ 이 링크 그룹 해제': '↗ Ungroup this link',
            '메쉬 면 중심/법선': 'Mesh face center/normal',
            '아직 3D에서 다시 지정하지 않았습니다.': 'Not yet reassigned in 3D.',
            '조인트 원점·축 재설정': 'Reset joint origin & axis',
            '↺ 조립품 원래 자세로 복원': '↺ Restore original assembly pose',
            '클릭 판정에 남길 부품': 'Parts available for picking',
            '겹친 자석 선택': 'Select overlapping snap',
            '마우스를 원·호 위로 옮기세요': 'Move the pointer over a circle or arc',
            '◀ 이전 자석': '◀ Previous snap',
            '다음 자석 ▶': 'Next snap ▶',
            '↕ 조인트 축 방향 뒤집기': '↕ Flip joint axis',
            '👁 자식 링크만 보기': '👁 Show child link only',
            '🌐 전체 부품 보기': '🌐 Show all parts',
            '⚙️ 이 연결을 실제 조인트로 사용': '⚙️ Use this connection as an actual joint',
            '조인트 이름': 'Joint name',
            '동작 메커니즘 (Type)': 'Motion mechanism (Type)',
            '회전/이동 축 (Axis)': 'Rotation/translation axis (Axis)',
            'Fusion 축 후보': 'Fusion axis candidates',
            '조인트 원점 회전 RPY (deg)': 'Joint-origin rotation RPY (deg)',
            '✂ 이 조인트 배선 끊기': '✂ Disconnect this joint',
            '숫자를 입력하세요.': 'Enter a number.',
            '0보다 큰 값을 입력하세요.': 'Enter a value greater than 0.',
            '최소값은 최대값보다 작아야 합니다.': 'The minimum must be less than the maximum.',
            '최대값은 최소값보다 커야 합니다.': 'The maximum must be greater than the minimum.',
            'RViz 실행 중': 'RViz running',
            'RViz 다시 열기': 'Reopen RViz',
            '동기화·빌드 중...': 'Syncing & building...',
            'MoveIt 상태 확인 중': 'Checking MoveIt status',
            'ROS 2 패키지 다운로드': 'Download ROS 2 package',
            'RViz 열기': 'Open RViz',
            'RViz 종료': 'Stop RViz',
            'MoveIt 설정 및 검사': 'MoveIt setup and validation',
            'Assistant에서 설정한 뒤 같은 작업공간을 정규화하고 실제 움직임을 검사합니다.': 'Configure in Assistant, then normalize the same workspace and validate actual motion.',
            '1. Assistant 설정': '1. Configure in Assistant',
            '2. 정규화·실행': '2. Normalize & run',
            '3. 움직임 자동검사': '3. Automatic motion test',
            'MoveIt 종료': 'Stop MoveIt',
            'URDF 생성이 완료되었습니다': 'URDF generation complete',
            '저장 위치 · ROS 2 작업공간': 'Save location · ROS 2 workspace',
            'RViz에서 모델 확인': 'Inspect model in RViz',
            'Ubuntu 22.04 WSL로 최신 패키지를 동기화하고 RViz를 실행합니다.': 'Sync the latest package to Ubuntu 22.04 WSL and launch RViz.'
        });

        const PETASOS_ENGLISH_PATTERNS = [
            [/^현재 저장 작업: (.+) · 클릭하여 다른 작업으로 전환$/, 'Current saved work: $1 · Click to switch'],
            [/^현재 프로젝트: (.+) · 클릭하여 저장 작업 불러오기$/, 'Current project: $1 · Click to load saved work'],
            [/^현재 작업 (.+) · 저장 작업 선택$/, 'Current work $1 · Select saved work'],
            [/^저장 · 현재 작업: (.+)$/, 'Save · Current work: $1'],
            [/^'(.+)' 작업으로 전환할까요\?$/, "Switch to '$1'?"],
            [/^'(.+)' 저장 작업을 현재 상태로 덮어쓸까요\?$/, "Overwrite '$1' with the current state?"],
            [/^'(.+)' 작업을 불러올까요\? 현재 화면은 선택한 저장 상태로 바뀝니다\.$/, "Load '$1'? The current screen will be replaced with the selected saved state."],
            [/^'(.+)' 불러오는 중\.\.\.$/, "Loading '$1'..."],
            [/^'(.+)' 저장 중\.\.\.$/, "Saving '$1'..."],
            [/^'(.+)' 저장에 실패했습니다\.$/, "Failed to save '$1'."],
            [/^'(.+)' 작업을 저장했습니다\.$/, "Saved '$1'."],
            [/^'(.+)'에 이어 저장하는 중\.\.\.$/, "Saving updates to '$1'..."],
            [/^'(.+)' 이어 저장에 실패했습니다\.$/, "Failed to save updates to '$1'."],
            [/^'(.+)'에 현재 작업을 이어 저장했습니다\.$/, "Saved the current work to '$1'."],
            [/^(\d+)개 부품과 (\d+)개 조인트를 Inventor에서 가져왔습니다\.$/, 'Imported $1 parts and $2 joints from Inventor.'],
            [/^(\d+)개 부품과 (\d+)개 조인트를 가져왔습니다\.$/, 'Imported $1 parts and $2 joints.'],
            [/^가져오기 완료 · (\d+)개 확인 항목이 있습니다\.$/, 'Import complete · $1 items need review.'],
            [/^저장된 바닥면: (.+)$/, 'Saved ground plane: $1'],
            [/^허용 범위 (.+)° ~ (.+)°$/, 'Allowed range $1° to $2°'],
            [/^리밋 지정 중 · 최소 (.+) \/ 최대 (.+)$/, 'Setting limits · min $1 / max $2'],
            [/^현재 (.+)° → 최소$/, 'Current $1° → minimum'],
            [/^현재 (.+)° → 최대$/, 'Current $1° → maximum'],
            [/^(.+) 링크만 표시합니다\. 내부 면을 선택한 뒤 전체 보기를 누르세요\.$/, 'Showing only link $1. Select an internal face, then click Show all.'],
            [/^(.+) 집중 보기 해제 · 전체 부품 보기$/, 'Exit $1 focus · show all parts'],
            [/^(.+) 부품만 집중 보기 · 다시 더블클릭하면 전체 보기$/, 'Focus on part $1 · double-click again to show all'],
            [/^🎯 선택 링크 다시 찾기: (.+)$/, '🎯 Find selected link: $1'],
            [/^(.+) 링크를 트리 중앙으로 이동$/, 'Center link $1 in the tree'],
            [/^원점 지정 완료: (.+)$/, 'Origin set: $1'],
            [/^이 부품만 화면과 클릭 판정에 남김: (.+)$/, 'Only this part remains visible and pickable: $1'],
            [/^자식 링크의 (\d+)개 부품만 화면과 클릭 판정에 남김$/, 'Only $1 child-link parts remain visible and pickable'],
            [/^(.+) · 이 부품만 판정: (.+)$/, '$1 · Pick only this part: $2'],
            [/^(.+) · (\d+)개 부품에서 판정$/, '$1 · Pick from $2 parts'],
            [/^겹친 자석 (\d+)개 — 목록에서 안쪽 원·호를 직접 고르세요\.$/, '$1 overlapping snaps — select the inner circle/arc from the list.'],
            [/^(.+) 부품만 남겼습니다\. 원하는 원·호로 마우스를 옮기세요\.$/, 'Only part $1 remains. Move the pointer over the desired circle or arc.'],
            [/^자식 링크의 (\d+)개 부품만 남겼습니다\. 겹친 후보는 아래 목록에서 고르세요\.$/, 'Only $1 child-link parts remain. Select overlapping candidates below.'],
            [/^부품 (\d+)개 선택 · 우클릭하여 한 링크로 그룹화$/, '$1 parts selected · right-click to group into one link'],
            [/^(.+) 선택 · 소속 링크: (.+)$/, '$1 selected · link: $2'],
            [/^선택 부품 (\d+)개 · 링크 (\d+)개$/, '$1 selected parts · $2 links'],
            [/^선택한 (\d+)개 링크를 하나로 그룹화$/, 'Group the $1 selected links into one'],
            [/^연결 링크 (\d+)개 · 조인트 (\d+)개(.*)$/, '$1 connected links · $2 joints$3'],
            [/^배선 완료 · 링크 (\d+)개 \/ 조인트 (\d+)개$/, 'Connections complete · $1 links / $2 joints'],
            [/^링크 (\d+) · 배선 (\d+) · 미연결 (\d+)$/, 'Links $1 · connections $2 · unconnected $3'],
            [/^(.+) 링크 노드$/, '$1 link node'],
            [/^(.+) 새 분기 출력 포트$/, '$1 new branch output port'],
            [/^(.+) 입력 포트$/, '$1 input port'],
            [/^(.+) 출력 포트$/, '$1 output port'],
            [/^선택 (\d+)개 병합$/, 'Merge $1 selected'],
            [/^그룹화 선택 (\d+)개 · 병합 후 남을 링크: (.+)$/, '$1 selected for grouping · surviving link: $2'],
            [/^놓으면 (.+) 링크에 합쳐집니다\.$/, 'Drop to merge into link $1.'],
            [/^총 (\d+)개 링크$/, '$1 links total'],
            [/^(.+) 링크 이름$/, '$1 link name'],
            [/^링크 이름 '(.+)'은 이미 사용 중입니다\.$/, "Link name '$1' is already in use."],
            [/^WORLD 루트 미지정 · 미연결 링크 (\d+)개$/, 'WORLD root not set · $1 unconnected links'],
            [/^(.+)로 연결된 (.+)$/, '$2 connected to $1'],
            [/^(.+) → (.+) 분기 출력 (\d+)$/, '$1 → $2 branch output $3'],
            [/^자식 링크 전체 \((\d+)개 부품\)$/, 'Entire child link ($1 parts)'],
            [/^최대 힘 \((.+)\)$/, 'Maximum effort ($1)'],
            [/^최대 속도 \((.+)\)$/, 'Maximum velocity ($1)'],
            [/^자석 중심: (.+) · 클릭하면 이 점이 조인트 원점, 면의 법선이 축이 됩니다\.$/, 'Snap center: $1 · Click to use this point as the joint origin and the face normal as its axis.'],
            [/^자석 중심: (.+) · 클릭하면 월드 XYZ 0,0,0이 됩니다\.$/, 'Snap center: $1 · Click to set world XYZ to 0,0,0.'],
            [/^원점 지정 완료: (.+)$/, 'Origin set: $1'],
            [/^1\/2 부모 연결점 저장 완료: (.+) · 이제 2\/2 자식 연결점을 선택하세요\.$/, '1/2 parent connection saved: $1 · Now select the 2/2 child connection point.'],
            [/^완료: 부모·자식 연결 프레임을 결합했습니다\. 두 연결점 간격 (.+) m · 조인트 원점은 두 점의 중앙입니다\.$/, 'Complete: combined the parent and child connection frames. Distance: $1 m · The joint origin is midway between the points.'],
            [/^완료: (.+) m · 빨강 X\/초록 Y는 평면 안, 파랑 Z는 면 법선입니다\.$/, 'Complete: $1 m · Red X/green Y lie in the plane; blue Z is the face normal.'],
            [/^그룹 해제 완료 · (.+)은 기존 연결을 유지하고, 나머지 (\d+)개 부품은 미연결 카드로 분리했습니다\.$/, 'Ungrouped · $1 kept existing connections; the other $2 parts became unconnected cards.'],
            [/^(.+) 분리 완료 · 이 부품을 기준으로 찍은 조인트 (\d+)개는 중심·축을 다시 확인하세요\.$/, 'Separated $1 · Recheck the center and axis of $2 joints picked from this part.'],
            [/^(.+) 부품을 (.+)에서 빼내 미연결 카드로 만들었습니다\.$/, 'Removed part $1 from $2 and created an unconnected card.'],
            [/^'(.+)' 부품을 '(.+)' 링크에서 빼낼까요\?$/, "Remove part '$1' from link '$2'?"],
            [/^URDF 생성 전 (.+)$/, 'Before generating URDF: $1'],
            [/^아직 묶음 후보 (\d+)개가 남아 있습니다\.$/, '$1 grouping candidates remain.'],
            [/^내보내기 폴더를 찾을 수 없습니다: (.+)$/, 'Export folder not found: $1'],
            [/^WSL로 전달할 수 없는 Windows 경로입니다: (.+)$/, 'This Windows path cannot be passed to WSL: $1'],
            [/^ROS 2 패키지 이름이 올바르지 않습니다: (.+)$/, 'Invalid ROS 2 package name: $1'],
            [/^올바르지 않은 ROS 2 패키지 이름입니다: (.+)$/, 'Invalid ROS 2 package name: $1'],
            [/^원본 조립품 파일을 찾을 수 없습니다: (.+)$/, 'Original assembly file not found: $1'],
            [/^저장된 프리뷰 편집 파일을 읽지 못했습니다: (.+)$/, 'Could not read the saved preview editing file: $1'],
            [/^(.+) 작업 파일을 찾을 수 없습니다\.$/, 'Work file not found: $1.'],
            [/^프리뷰 작업 저장 실패: (.+)$/, 'Failed to save preview work: $1'],
            [/^프리뷰 작업 불러오기 실패: (.+)$/, 'Failed to load preview work: $1'],
            [/^가져오기 실패: (.+)$/, 'Import failed: $1'],
            [/^현재 Inventor 가져오기 실패: (.+)$/, 'Failed to import the current Inventor assembly: $1'],
            [/^원본 IAM 가져오기 실패: (.+)$/, 'Failed to import the original IAM: $1'],
            [/^URDF 생성 실패: (.+)$/, 'URDF generation failed: $1'],
            [/^MoveIt 계획\/실행 실패: (.+)$/, 'MoveIt planning/execution failed: $1'],
            [/^상태 확인 실패: (.+)$/, 'Status check failed: $1'],
            [/^MoveIt 상태 확인 실패: (.+)$/, 'MoveIt status check failed: $1']
        ];

        const PETASOS_ENGLISH_SENTENCES = [
            ['미연결 링크 ·', 'Unconnected link ·'], ['링크 ·', 'Link ·'], ['조인트 ·', 'Joint ·'],
            ['와(과) 연결됨 (', 'connected to ('],
            ['정확 스냅', 'precise snap'], ['겹친 후보', 'overlapping candidates'], ['다음 후보', 'next candidate'],
            ['원/호 중심 자석', 'circle/arc center snap'], ['긴 모서리 방향 감지', 'long-edge direction detected'],
            ['원형/대칭면은 부모 링크 X방향 사용', 'using the parent-link X direction for circular/symmetric faces'],
            ['사용자 지정 면', 'custom face'], ['긴 모서리 → 월드', 'long edge → world'], ['평면 내 회전 유지', 'keep in-plane rotation'],
            ['부모 링크 전체', 'entire parent link'], ['자식 링크 전체', 'entire child link'], ['개 부품', ' parts'],
            ['이 부품만 화면과 클릭 판정에 남김:', 'Only this part remains visible and pickable:'], ['이 부품만 판정:', 'pick only this part:'],
            ['부품에서 판정', 'parts available for picking'], ['겹친 자석', 'overlapping snaps'],
            ['부품만 남겼습니다.', 'part remains.'], ['자식 링크 밖의 부품을 완전히 제외했습니다.', 'Completely excluded parts outside the child link.'],
            ['정밀 CAD 자석', 'precise CAD snaps'], ['원·호를 고르세요.', 'Choose the desired circle or arc.'],
            ['이 프로젝트에는 정밀 CAD 자석이 없으므로 IAM을 다시 가져와야 원·호 중심이 정확해집니다.', 'This project has no precise CAD snaps; reimport the IAM for accurate circle/arc centers.'],
            ['1/2 부모 연결점:', '1/2 parent connection:'], ['부모 링크의 원·호 중심 또는 평면 중심을 선택하세요.', 'Select a circle/arc center or face center on the parent link.'],
            ['부모 연결점 저장 완료:', 'Parent connection saved:'], ['이제 2/2 자식 연결점을 선택하세요.', 'Now select the 2/2 child connection point.'],
            ['부품 선택 · 우클릭하여 한 링크로 그룹화', 'parts selected · right-click to group into one link'],
            ['그룹화 선택', 'Grouping selection'], ['병합 후 남을 링크:', 'surviving link:'],
            ['미연결 카드로 분리했습니다.', 'separated into unconnected cards.'], ['이 연결은 IAM 배치 보존용 묶음 후보입니다.', 'This connection is a grouping candidate that preserves the IAM layout.'],
            ['같은 링크의 부품이면 카드를 겹쳐 합치고, 서로 움직이는 링크 사이면 아래 버튼으로 실제 조인트로 전환하세요.', 'If the parts belong to one link, overlap the cards to merge them; if the links move relative to each other, convert this to an actual joint below.'],
            ['WORLD 루트 미지정 ·', 'WORLD root not set ·'], ['미연결 링크', 'unconnected links'], ['중복 조인트 이름', 'duplicate joint names'],
            ['리밋 미완료', 'incomplete limits'], ['lower ≥ upper 오류', 'lower ≥ upper errors'],
            ['WORLD를 사용할 루트 링크에 연결하세요', 'connect the root link to WORLD'], ['개를 배선하거나 병합하세요', 'must be connected or merged'],
            ['개를 수정하세요', 'must be corrected'], ['회전 리밋 미완료', 'incomplete rotation limits'], ['개의 최소·최대값을 모두 지정하세요', 'need both minimum and maximum values'],
            ['리밋 오류', 'limit errors'], ['개에서 lower를 upper보다 작게 설정하세요', 'must set lower below upper'],
            ['같은 링크의 부품은 카드를 겹쳐 병합하고, 링크 사이 연결은 묶음 후보를 클릭해 실제 조인트로 전환하세요.', 'Merge parts of the same link by overlapping their cards; for a connection between links, click the grouping candidate and convert it to an actual joint.'],
            ['저장 중...', 'Saving...'], ['저장 완료', 'Saved'], ['저장 실패', 'Save failed'],
            ['작업 저장에 실패했습니다.', 'Failed to save work.'], ['저장 작업 목록을 읽지 못했습니다.', 'Could not read the saved-work list.'],
            ['저장된 작업이 없습니다.', 'No saved work.'], ['저장 작업을 불러오지 못했습니다.', 'Could not load saved work.'],
            ['저장 목록을 읽지 못했습니다.', 'Could not read the saved-work list.'], ['아직 이름을 붙여 저장한 작업이 없습니다.', 'No named saved work yet.'],
            ['저장 목록 불러오기 실패', 'Failed to load saved-work list'], ['저장 작업 이름을 입력하세요.', 'Enter a saved-work name.'],
            ['먼저 새 저장 작업 이름을 만들어주세요.', 'Create a new saved-work name first.'], ['불러올 저장 작업을 목록에서 선택하세요.', 'Select work to load from the list.'],
            ['이전 작업 목록을 읽지 못했습니다.', 'Could not read the previous-work list.'], ['이전 작업 목록 불러오기 실패', 'Failed to load previous-work list'],
            ['불러올 이전 작업을 선택하세요.', 'Select previous work to load.'], ['이전 작업을 불러오지 못했습니다.', 'Could not load previous work.'],
            ['프로젝트 이름을 입력하세요.', 'Enter a project name.'], ['현재 Inventor 조립품과 참조 부품을 읽고 있습니다...', 'Reading the current Inventor assembly and referenced parts...'],
            ['Windows 파일 선택창에서 원본 IAM을 선택하세요...', 'Select the original IAM in the Windows file dialog...'], ['Inventor 가져오기에 실패했습니다.', 'Failed to import from Inventor.'],
            ['원본 IAM 선택을 취소했습니다.', 'Original IAM selection canceled.'], ['프로젝트 이름과 조립품 파일 또는 프로젝트 폴더가 필요합니다.', 'A project name and assembly file or project folder are required.'],
            ['IAM은 형상을 내장하지 않습니다. 아래 폴더 선택에서 IAM과 참조 IPT가 함께 있는 프로젝트 폴더 전체를 선택하세요.', 'IAM does not embed geometry. Select the entire project folder containing the IAM and referenced IPT files below.'],
            ['형상과 조립 정보를 분석하고 있습니다...', 'Analyzing geometry and assembly information...'], ['가져오기에 실패했습니다.', 'Import failed.'],
            ['비정상적으로 멀리 저장된 원점을 해제했습니다. 바닥면을 다시 지정하세요.', 'Cleared an abnormally distant saved origin. Set the ground plane again.'],
            ['CAD 원 중심', 'CAD circle center'], ['CAD 호 중심', 'CAD arc center'], ['CAD 원통 중심축', 'CAD cylinder axis'], ['CAD 면 중심', 'CAD face center'],
            ['CAD 모서리 중점', 'CAD edge midpoint'], ['CAD 꼭짓점', 'CAD vertex'], ['원/호 중심', 'Circle/arc center'], ['면 중심', 'Face center'],
            ['평평한 면 위로 마우스를 옮겨 노란 중심점이 나타나면 클릭하세요.', 'Move over a flat face and click when the yellow center point appears.'],
            ['바닥면 지정을 취소했습니다.', 'Ground-plane selection canceled.'], ['CAD 종류에 맞는 자동 위쪽 축으로 복원했습니다.', 'Restored the automatic up axis for this CAD type.'],
            ['위쪽 축을 적용했습니다. 필요하면 바닥면을 직접 지정할 수 있습니다.', 'Applied the up axis. You can set the ground plane manually if needed.'],
            ['조립품을 불러오면 3D 형상이 표시됩니다.', 'Import an assembly to display its 3D geometry.'],
            ['최소·최대 각도에는 숫자를 입력하세요.', 'Enter numbers for minimum and maximum angles.'], ['최소각은 설정된 최대각보다 작아야 합니다.', 'The minimum angle must be less than the maximum angle.'],
            ['최대각은 설정된 최소각보다 커야 합니다.', 'The maximum angle must be greater than the minimum angle.'],
            ['조립품을 처음 불러온 원래 자세로 복원했습니다.', 'Restored the original pose from when the assembly was imported.'], ['전체 링크 보기로 복원했습니다.', 'Restored the view of all links.'],
            ['면을 찾지 못했습니다. 모델의 평평한 면을 다시 클릭하세요.', 'No face found. Click a flat face on the model again.'], ['이 면의 방향을 계산하지 못했습니다. 다른 평평한 면을 선택하세요.', 'Could not calculate this face orientation. Select another flat face.'],
            ['평면 내 회전 유지', 'Keep in-plane rotation'], ['이 프로젝트는 IAM을 다시 가져와야 원·호 중심을 정밀하게 잡을 수 있습니다.', 'Reimport the IAM to locate circle and arc centers precisely in this project.'],
            ['조인트 위치 지정을 취소했습니다.', 'Joint placement canceled.'], ['선택한 조인트의 부모 링크를 찾지 못했습니다.', 'Could not find the parent link of the selected joint.'],
            ['CAD 스냅 또는 평면 중심을 찾지 못했습니다. 원·호 테두리나 평평한 면을 다시 클릭하세요.', 'Could not find a CAD snap or face center. Click a circle/arc edge or flat face again.'],
            ['선택 영역이 완전히 평평하지 않습니다. 베벨이나 곡면이 아닌 평면을 클릭하세요.', 'The selected area is not completely flat. Click a plane rather than a bevel or curved surface.'],
            ['이 면에서 직교 좌표계를 만들지 못했습니다. 더 넓고 평평한 면을 선택하세요.', 'Could not create an orthogonal frame from this face. Select a wider, flatter face.'],
            ['남길 링크와 합칠 링크들을 차례로 선택한 뒤 병합 버튼을 누르세요.', 'Select the link to keep and the links to merge, then click Merge.'],
            ['그룹 해제할 링크 카드를 먼저 선택하세요.', 'Select a link card to ungroup first.'], ['두 개 이상의 부품이 들어 있는 링크만 그룹 해제할 수 있습니다.', 'Only links containing two or more parts can be ungrouped.'],
            ['링크에는 최소 한 개의 부품이 남아 있어야 합니다.', 'At least one part must remain in a link.'], ['WORLD에 연결할 루트 링크의 입력 포트를 클릭하세요.', 'Click the input port of the root link to connect to WORLD.'],
            ['연결할 자식 링크의 왼쪽 입력 포트를 클릭하세요.', 'Click the left input port of the child link to connect.'], ['이 연결은 순환 구조를 만들기 때문에 사용할 수 없습니다.', 'This connection would create a cycle and cannot be used.'],
            ['끊을 조인트 선을 먼저 클릭하세요.', 'Click the joint connection to disconnect first.'], ['부모 링크의 출력 포트를 먼저 누른 뒤 이 입력 포트를 누르세요.', 'Click the parent link output port, then this input port.'],
            ['이 링크에서 자식 링크로 조인트 연결을 시작합니다.', 'Start a joint connection from this link to a child link.'],
            ['최신 ROS 2 패키지를 Ubuntu 22.04로 보내고 있습니다.', 'Sending the latest ROS 2 package to Ubuntu 22.04.'], ['WSL RViz를 시작하지 못했습니다.', 'Could not start WSL RViz.'],
            ['WSL 빌드를 시작했습니다.', 'Started the WSL build.'], ['RViz와 ROS 2 표시 노드를 종료하고 있습니다.', 'Stopping RViz and ROS 2 display nodes.'],
            ['RViz를 종료하지 못했습니다.', 'Could not stop RViz.'], ['RViz가 종료되었습니다.', 'RViz stopped.'],
            ['페타소스 MoveIt 시작 설정을 검사하고 Setup Assistant를 열고 있습니다.', 'Checking the Petasos MoveIt startup configuration and opening Setup Assistant.'],
            ['MoveIt Setup Assistant를 열지 못했습니다.', 'Could not open MoveIt Setup Assistant.'], ['MoveIt Assistant 준비 중', 'Preparing MoveIt Assistant'],
            ['Assistant 저장 결과를 백업·정규화한 뒤 MoveIt 데모를 빌드하고 있습니다.', 'Backing up and normalizing the Assistant output, then building the MoveIt demo.'],
            ['MoveIt 데모를 실행하지 못했습니다.', 'Could not run the MoveIt demo.'], ['MoveIt 데모 준비 중', 'Preparing MoveIt demo'],
            ['현재 관절 상태에서 안전한 작은 목표를 만들어 계획·실행하고 있습니다.', 'Planning and executing a small safe target from the current joint state.'],
            ['MoveIt 움직임 검사에 실패했습니다.', 'MoveIt motion validation failed.'], ['MoveIt 움직임 검사 성공', 'MoveIt motion validation succeeded'],
            ['MoveIt 작업을 종료하고 있습니다.', 'Stopping MoveIt tasks.'], ['MoveIt 작업을 종료하지 못했습니다.', 'Could not stop MoveIt tasks.'], ['MoveIt 작업을 종료했습니다.', 'MoveIt tasks stopped.'],
            ['URDF 생성에 실패했습니다.', 'URDF generation failed.'], ['선택한 경로', 'Selected path'],
            ['description과 moveit_config가 start_petasos.cmd 옆 export/ros_ws/src에 생성되었습니다. Assistant가 이 작업공간을 직접 수정합니다.', 'The description and moveit_config packages were created in export/ros_ws/src beside start_petasos.cmd. Assistant edits this workspace directly.'],
            ['MoveIt 없이 사용할 수 있는 ROS 2 기본 description 패키지가 생성되었습니다.', 'A basic ROS 2 description package that works without MoveIt was created.'],
            ['이 브라우저 창을 닫고 Fusion 360으로 돌아가시면 생성이 진행됩니다.', 'Close this browser window and return to Fusion 360 to continue generation.'],
            ['RViz 실행 대기 중', 'Waiting to launch RViz'], ['RViz 실행 스크립트를 Ubuntu에 준비하지 못했습니다.', 'Could not prepare the RViz launch script in Ubuntu.'],
            ['RViz가 Windows 화면에서 실행 중입니다.', 'RViz is running on the Windows desktop.'], ['RViz 실행이 종료되었습니다.', 'RViz has stopped.'],
            ['RViz 실행 중 오류가 발생했습니다.', 'An error occurred while running RViz.'], ['동기화 또는 빌드 중 오류가 발생했습니다.', 'An error occurred during synchronization or build.'],
            ['내보낸 ROS 2 package.xml을 찾을 수 없습니다.', 'The exported ROS 2 package.xml was not found.'], ['이미 RViz가 실행 중입니다.', 'RViz is already running.'],
            ['WSL로 패키지를 복사하고 ROS 2 빌드를 준비하고 있습니다.', 'Copying the package to WSL and preparing the ROS 2 build.'], ['실행 중인 RViz가 없습니다.', 'RViz is not running.'],
            ['원본 IAM 파일 선택은 Windows에서 지원됩니다.', 'Selecting an original IAM file is supported on Windows.'], ['Windows 파일 선택창을 사용할 수 없습니다.', 'The Windows file dialog is unavailable.'],
            ['먼저 조립품을 불러와야 합니다.', 'Import an assembly first.'], ['저장할 프리뷰 편집 데이터가 올바르지 않습니다.', 'The preview editing data to save is invalid.'],
            ['불러올 프로젝트 경로가 올바르지 않습니다.', 'The project path to load is invalid.'], ['불러올 프로젝트를 찾을 수 없습니다.', 'The project to load was not found.'],
            ['다시 불러올 프로젝트가 없습니다.', 'There is no project to reload.'], ['불러올 저장 작업 이름이 올바르지 않습니다.', 'The saved-work name to load is invalid.'],
            ['마지막 자동 저장', 'Last autosave'], ['저장된 프리뷰 편집 데이터가 올바르지 않습니다.', 'The saved preview editing data is invalid.'],
            ['지원되는 파일이 선택되지 않았습니다.', 'No supported file was selected.'], ['ZIP 내보내기는 사용하지 않습니다. export/ros_ws 폴더를 직접 사용하세요.', 'ZIP export is not used. Use the export/ros_ws folder directly.'],
            ['먼저 ROS 2 패키지를 생성해 주세요.', 'Generate the ROS 2 package first.'], ['내보낸 description 패키지를 찾지 못했습니다.', 'The exported description package was not found.'],
            ['기본 ROS 2 패키지로 익스포트했습니다. MoveIt 단일 ros_ws를 선택해 다시 생성하세요.', 'The basic ROS 2 package was exported. Select the MoveIt unified ros_ws option and generate again.'],
            ['기본 ROS 2 패키지에는 MoveIt 설정이 없습니다.', 'The basic ROS 2 package does not include MoveIt configuration.'], ['RViz와 MoveIt 세션을 정리했습니다.', 'RViz and MoveIt sessions were cleaned up.'],
            ['MoveIt 테스트 대기 중', 'Waiting for MoveIt test'], ['Ubuntu 22.04에 MoveIt 또는 MoveIt Setup Assistant가 없습니다.', 'MoveIt or MoveIt Setup Assistant is not installed in Ubuntu 22.04.'],
            ['이미 MoveIt 작업이 실행 중입니다.', 'A MoveIt task is already running.'], ['MoveIt Assistant에 전달할 로봇 xacro 파일을 찾지 못했습니다.', 'The robot xacro file for MoveIt Assistant was not found.'],
            ['내보낸 ROS 2 패키지에서 package.xml을 찾지 못했습니다.', 'package.xml was not found in the exported ROS 2 package.'],
            ['MoveIt 설정 패키지를 찾지 못했습니다.', 'The MoveIt configuration package was not found.'], ['경로로 생성한 뒤 다시 실행하세요.', 'Create it at this path, then run again.'],
            ['Assistant 저장 결과에서 실행 전 문제가 발견됐습니다:', 'Pre-run issues were found in the Assistant output:'], ['상세 로그를 확인하세요.', 'Check the detailed log.'],
            ['MoveIt Assistant 메타데이터가 불완전합니다.', 'MoveIt Assistant metadata is incomplete.'], ['MoveIt 단일 ros_ws를 다시 내보낸 뒤 실행하세요.', 'Export the MoveIt unified ros_ws again, then run.'],
            ['페타소스 MoveIt 시작 설정을 열었습니다. 그룹·충돌·포즈를 편집하고 저장한 뒤 창을 닫으세요.', 'Petasos MoveIt startup settings are open. Edit and save groups, collisions, and poses, then close the window.'],
            ['MoveIt demo.launch.py가 실행 중입니다.', 'MoveIt demo.launch.py is running.'], ['Assistant 저장 결과 검사 및 ros_ws 익스포트 완료', 'Assistant output validation and ros_ws export complete'],
            ['이제 ‘생성 결과 실행’을 누르세요.', 'Now click “Run generated result”.'], ['Assistant를 닫았습니다. ros_ws 저장 결과를 확인하세요.', 'Assistant closed. Check the saved ros_ws output.'],
            ['MoveIt 데모가 종료되었습니다.', 'The MoveIt demo has stopped.'], ['MoveIt 실행 중 오류가 발생했습니다.', 'An error occurred while running MoveIt.'],
            ['WSL 복사·빌드 중 오류가 발생했습니다.', 'An error occurred during WSL copy/build.'], ['같은 ros_ws 폴더에서 MoveIt 설정 패키지를 찾지 못했습니다.', 'The MoveIt configuration package was not found in the same ros_ws folder.'],
            ['MoveIt 단일 ros_ws를 다시 익스포트하세요.', 'Export the MoveIt unified ros_ws again.'], ['내보낸 ros_ws의 Xacro와 MoveIt 설정을 직접 검사한 뒤', 'Inspecting Xacro and MoveIt settings in the exported ros_ws, then'],
            ['MoveIt Setup Assistant를 준비하고 있습니다.', 'preparing MoveIt Setup Assistant.'], ['설정 위치:', 'Configuration location:'],
            ['Assistant 결과를 백업·정규화한 뒤', 'Backing up and normalizing Assistant output, then'], ['ROS 2 작업공간을 빌드하고 있습니다.', 'building the ROS 2 workspace.'],
            ['먼저 MoveIt 생성 결과를 실행해 demo를 켜 주세요.', 'Run the generated MoveIt result and start the demo first.'], ['MoveIt 자동검사에 필요한 패키지 정보를 찾지 못했습니다.', 'Package information required for MoveIt automatic validation was not found.'],
            ['MoveIt 자동 움직임 검사에 실패했습니다.', 'MoveIt automatic motion validation failed.'], ['움직임 검사 성공:', 'Motion validation succeeded:'],
            ['OMPL 계획과 가상 컨트롤러 실행 후', 'after OMPL planning and virtual controller execution,'], ['최대 관절 오차', 'maximum joint error'],
            ['실행 중인 MoveIt 작업이 없습니다.', 'No MoveIt task is running.']
        ];

        function petasosTranslateText(value) {
            const source = String(value ?? '');
            if (petasosLanguage !== 'en' || !/[가-힣]/.test(source)) return source;
            const leading = source.match(/^\s*/)[0];
            const trailing = source.match(/\s*$/)[0];
            const compact = source.trim().replace(/\s+/g, ' ');
            if (PETASOS_ENGLISH[compact]) return leading + PETASOS_ENGLISH[compact] + trailing;
            let translated = compact;
            for (const [pattern, replacement] of PETASOS_ENGLISH_PATTERNS) {
                if (pattern.test(translated)) {
                    translated = translated.replace(pattern, replacement);
                    break;
                }
            }
            for (const [ko, en] of PETASOS_ENGLISH_SENTENCES) translated = translated.split(ko).join(en);
            return leading + translated + trailing;
        }

        function petasosTranslateNode(root) {
            if (!root || (root.nodeType === Node.ELEMENT_NODE && root.closest('[data-no-i18n]'))) return;
            if (root.nodeType === Node.TEXT_NODE) {
                const value = root.nodeValue || '';
                if (/[가-힣]/.test(value)) petasosTextOriginals.set(root, value);
                if (petasosLanguage === 'en') root.nodeValue = petasosTranslateText(value);
                return;
            }
            if (root.nodeType !== Node.ELEMENT_NODE && root.nodeType !== Node.DOCUMENT_FRAGMENT_NODE) return;
            if (root.nodeType === Node.ELEMENT_NODE) {
                let originals = petasosAttributeOriginals.get(root);
                for (const name of PETASOS_TRANSLATED_ATTRIBUTES) {
                    if (!root.hasAttribute(name)) continue;
                    const value = root.getAttribute(name) || '';
                    if (/[가-힣]/.test(value)) {
                        if (!originals) originals = new Map();
                        originals.set(name, value);
                        petasosAttributeOriginals.set(root, originals);
                    }
                    if (petasosLanguage === 'en') root.setAttribute(name, petasosTranslateText(value));
                }
            }
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
            let node;
            while ((node = walker.nextNode())) {
                if (node.nodeType === Node.ELEMENT_NODE) {
                    if (node.hasAttribute('data-no-i18n')) {
                        walker.currentNode = node;
                        continue;
                    }
                    let originals = petasosAttributeOriginals.get(node);
                    for (const name of PETASOS_TRANSLATED_ATTRIBUTES) {
                        if (!node.hasAttribute(name)) continue;
                        const value = node.getAttribute(name) || '';
                        if (/[가-힣]/.test(value)) {
                            if (!originals) originals = new Map();
                            originals.set(name, value);
                            petasosAttributeOriginals.set(node, originals);
                        }
                        if (petasosLanguage === 'en') node.setAttribute(name, petasosTranslateText(value));
                    }
                } else if (!node.parentElement?.closest('[data-no-i18n]')) {
                    const value = node.nodeValue || '';
                    if (/[가-힣]/.test(value)) petasosTextOriginals.set(node, value);
                    if (petasosLanguage === 'en') node.nodeValue = petasosTranslateText(value);
                }
            }
        }

        function petasosRestoreKorean(root = document.body) {
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
            const nodes = [root];
            let node;
            while ((node = walker.nextNode())) nodes.push(node);
            for (const current of nodes) {
                if (current.nodeType === Node.TEXT_NODE) {
                    const original = petasosTextOriginals.get(current);
                    if (original !== undefined) current.nodeValue = original;
                } else if (current.nodeType === Node.ELEMENT_NODE) {
                    const originals = petasosAttributeOriginals.get(current);
                    if (originals) for (const [name, value] of originals) current.setAttribute(name, value);
                }
            }
        }

        function petasosUpdateLanguageButtons() {
            const english = document.getElementById('language-en');
            const korean = document.getElementById('language-ko');
            if (!english || !korean) return;
            english.classList.toggle('active', petasosLanguage === 'en');
            korean.classList.toggle('active', petasosLanguage === 'ko');
            english.setAttribute('aria-pressed', String(petasosLanguage === 'en'));
            korean.setAttribute('aria-pressed', String(petasosLanguage === 'ko'));
        }

        function setPetasosLanguage(language, persist = true) {
            petasosLanguage = language === 'en' ? 'en' : 'ko';
            document.documentElement.lang = petasosLanguage;
            petasosApplyingLanguage = true;
            if (petasosLanguage === 'en') {
                petasosTranslateNode(document.body);
                document.title = 'Petasos A3 · URDF Structure Editor';
            } else {
                petasosRestoreKorean();
                document.title = '페타소스 A3 · URDF 구조 에디터';
            }
            petasosUpdateLanguageButtons();
            if (persist) {
                try { localStorage.setItem(PETASOS_LANGUAGE_KEY, petasosLanguage); } catch (_) {}
            }
            queueMicrotask(() => { petasosApplyingLanguage = false; });
            document.dispatchEvent(new CustomEvent('petasoslanguagechange', { detail: { language: petasosLanguage } }));
        }

        function petasosI18nAudit() {
            const issues = [];
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
            let node;
            while ((node = walker.nextNode())) {
                if (node.nodeType === Node.TEXT_NODE && node.parentElement?.closest('[data-no-i18n]')) continue;
                if (node.nodeType === Node.TEXT_NODE && /[가-힣]/.test(node.nodeValue || '')) issues.push(node.nodeValue.trim());
                if (node.nodeType === Node.ELEMENT_NODE && !node.closest('[data-no-i18n]')) {
                    for (const name of PETASOS_TRANSLATED_ATTRIBUTES) {
                        const value = node.getAttribute(name) || '';
                        if (/[가-힣]/.test(value)) issues.push(`${name}: ${value}`);
                    }
                }
            }
            return [...new Set(issues.filter(Boolean))];
        }
        window.petasosI18nAudit = petasosI18nAudit;

        const petasosLanguageObserver = new MutationObserver(mutations => {
            if (petasosApplyingLanguage) return;
            petasosApplyingLanguage = true;
            for (const mutation of mutations) {
                if (mutation.type === 'characterData') petasosTranslateNode(mutation.target);
                else if (mutation.type === 'attributes') petasosTranslateNode(mutation.target);
                else for (const added of mutation.addedNodes) petasosTranslateNode(added);
            }
            queueMicrotask(() => { petasosApplyingLanguage = false; });
        });

        const petasosNativeAlert = window.alert.bind(window);
        const petasosNativeConfirm = window.confirm.bind(window);
        window.alert = message => petasosNativeAlert(petasosTranslateText(message));
        window.confirm = message => petasosNativeConfirm(petasosTranslateText(message));

        document.addEventListener('DOMContentLoaded', () => {
            try { petasosLanguage = localStorage.getItem(PETASOS_LANGUAGE_KEY) === 'en' ? 'en' : 'ko'; } catch (_) {}
            petasosTranslateNode(document.body);
            setPetasosLanguage(petasosLanguage, false);
            petasosLanguageObserver.observe(document.body, {
                subtree: true, childList: true, characterData: true, attributes: true,
                attributeFilter: PETASOS_TRANSLATED_ATTRIBUTES
            });
        });

        let treeData = null;
        let selectedElement = null;
        let selectedPhysicalMaterialKey = null;
        let physicalMaterialLibraryExpanded = false;
        let patcherMaterialShelfExpanded = false;
        let patcherMaterialShelfQuery = '';
        let patcherMaterialCreateOpen = false;
        let panelSelectionIdentity = null;
        let activePhysicalMaterialComponent = null;
        let activePhysicalMaterialKey = '';
        let structureNamingPlan = null;
        let structureNamingContinueExport = false;
        const TREE_EDITOR_MODE = false;

        // --- 3D 프리뷰 관련 변수 ---
        let scene, camera, renderer, controls, robotRoot;
        let worldFrameHelper, gridHelper, baseFootprintFrameMarker;
        let meshDict = {}; // { 'comp_name': THREE.Mesh }
        let meshComponentByObject = new WeakMap();
        let meshEdgeDict = {};
        let collisionMeshDict = {};
        let jointFrameHelpers = [];
        let linkFrameHelpers = [];
        let inertiaMarkers = [];
        let previewJointControllers = [];
        let previewPivotGroups = [];
        let expandedPreviewJointDetails = new Set();
        let previewJointGesture = null;
        let viewerCameraGesture = null;
        let pendingPreviewPoseRestore = null;
        let previewRigReady = false;
        let previewRigDirty = false;
        let previewControlsDirty = false;
        let previewUpdateTimer = null;
        let viewerPointerDown = null;
        let viewerPointerDragged = false;
        let viewerRightPointerDown = null;
        let viewerRightPointerDragged = false;
        let viewerSingleClickTimer = null;
        let viewerSelectedComponent = null;
        let viewerSelectedComponents = new Set();
        let viewerIsolatedNode = null;
        let viewerIsolatedComponent = null;
        let visualMeshesEnabled = true;
        let collisionMeshesEnabled = false;
        let groundFacePickMode = false;
        let baseFootprintPickMode = false;
        let baseFootprintPanelExpanded = false;
        let baseFootprintFrameSelected = false;
        let jointOriginPickMode = false;
        let jointOriginPickJoint = null;
        let jointOriginPickStage = 'parent';
        let jointOriginParentSnap = null;
        let jointPickAllowedComponents = null;
        let jointPickTargetComponent = null;
        let jointSnapCandidateCache = [];
        let jointSnapSelectedKey = null;
        let jointSnapControlsSignature = '';
        let activeJointSnapMarkerInfo = null;
        let groundSnapMarker = null;
        let jointSnapMarker = null;
        let groundSnapHoverFrame = null;
        let groundSnapHoverEvent = null;
        let groundSnapLastHoverAt = 0;
        let groundPlanarSnapCache = new WeakMap();
        let suppressViewerDoubleClickUntil = 0;
        const detectedDeviceMemory = Number(navigator.deviceMemory) || 0;
        const detectedHardwareThreads = Number(navigator.hardwareConcurrency) || 0;
        const PETASOS_LOW_SPEC_RENDERING = (
            (detectedDeviceMemory > 0 && detectedDeviceMemory <= 4)
            || (detectedHardwareThreads > 0 && detectedHardwareThreads <= 4)
        );
        const PREVIEW_FRAME_INTERVAL_MS = PETASOS_LOW_SPEC_RENDERING ? (1000 / 24) : 0;
        let previewLastFrameAt = 0;
        let viewerResizeWidth = 0;
        let viewerResizeHeight = 0;
        let viewerResizeObserver = null;
        const pendingMeshEdgeJobs = [];
        let meshEdgeBuildTimer = null;
        const viewerRaycaster = new THREE.Raycaster();
        const viewerPointer = new THREE.Vector2();
        
        // 같은 링크에 합쳐진 부품은 동일한 색을 공유합니다.
        const LINK_GROUP_COLORS = [
            0xe76f51, 0x42a5f5, 0x66bb6a, 0xab47bc, 0xffca28,
            0x26c6da, 0xec407a, 0x8d6e63, 0x7e57c2, 0x9ccc65,
            0xff7043, 0x29b6f6, 0xd4e157, 0x5c6bc0, 0x26a69a
        ];
        let linkColorAssignments = new WeakMap();
        let nextLinkColorIndex = 0;
        const linkGroupMaterials = new Map();
        const defaultMaterial = new THREE.MeshPhongMaterial({
            color: 0x9ca3af,
            side: THREE.DoubleSide,
            flatShading: true,
            shininess: 28
        });
        const highlightMaterial = new THREE.MeshBasicMaterial({ color: 0x00aaff, wireframe: false, side: THREE.DoubleSide });
        const ghostMaterial = new THREE.MeshBasicMaterial({ color: 0x333333, transparent: true, opacity: 0.1, wireframe: true });

        function isLinkDisabled(targetNode) {
            if (!targetNode) return false;
            if (!treeData || targetNode === treeData) return false;
            if (targetNode.disabled) return true;

            function checkPath(current, ancestorDisabled) {
                if (!current) return null;
                const currentDisabled = ancestorDisabled || !!current.disabled;
                if (current === targetNode) {
                    return currentDisabled;
                }
                if (!Array.isArray(current.children)) return null;
                for (const child of current.children) {
                    const branchDisabled = currentDisabled || !!child.disabled;
                    if (child.link_group === targetNode) {
                        return branchDisabled || !!child.link_group?.disabled;
                    }
                    if (child.link_group) {
                        const found = checkPath(child.link_group, branchDisabled);
                        if (found !== null) return found;
                    }
                }
                return null;
            }

            const result = checkPath(treeData, !!treeData.disabled);
            return result === true;
        }

        function isJointDisabled(jointObj) {
            if (!jointObj) return false;
            if (jointObj.disabled) return true;
            if (jointObj.link_group && isLinkDisabled(jointObj.link_group)) return true;
            if (!treeData) return false;

            function checkJointAncestors(current, ancestorDisabled) {
                if (!current) return null;
                const currentDisabled = ancestorDisabled || !!current.disabled;
                if (!Array.isArray(current.children)) return null;
                for (const child of current.children) {
                    if (child === jointObj) {
                        return currentDisabled || !!child.disabled;
                    }
                    if (child.link_group) {
                        const found = checkJointAncestors(child.link_group, currentDisabled || !!child.disabled);
                        if (found !== null) return found;
                    }
                }
                return null;
            }

            const result = checkJointAncestors(treeData, !!treeData.disabled);
            return result === true;
        }

        function setSubtreeActive(node, willDisable) {
            if (!node) return;
            node.disabled = willDisable;
            if (Array.isArray(node.children)) {
                for (const child of node.children) {
                    child.disabled = willDisable;
                    if (child.link_group) {
                        setSubtreeActive(child.link_group, willDisable);
                    }
                }
            }
        }

        function syncIncomingJoint(parent, targetNode, willDisable) {
            if (!parent || !Array.isArray(parent.children)) return false;
            for (const child of parent.children) {
                if (child.link_group === targetNode) {
                    child.disabled = willDisable;
                    return true;
                }
                if (child.link_group && syncIncomingJoint(child.link_group, targetNode, willDisable)) {
                    return true;
                }
            }
            return false;
        }

        function enableAncestors(root, targetNode) {
            function findAndEnable(current) {
                if (!current || !Array.isArray(current.children)) return false;
                for (const child of current.children) {
                    if (child.link_group === targetNode) {
                        child.disabled = false;
                        current.disabled = false;
                        return true;
                    }
                    if (child.link_group && findAndEnable(child.link_group)) {
                        child.disabled = false;
                        current.disabled = false;
                        return true;
                    }
                }
                return false;
            }
            findAndEnable(root);
        }

        function enableJointAncestors(root, targetJoint) {
            function findAndEnable(current) {
                if (!current || !Array.isArray(current.children)) return false;
                for (const child of current.children) {
                    if (child === targetJoint) {
                        current.disabled = false;
                        return true;
                    }
                    if (child.link_group && findAndEnable(child.link_group)) {
                        child.disabled = false;
                        current.disabled = false;
                        return true;
                    }
                }
                return false;
            }
            findAndEnable(root);
        }

        function getDisabledComponents() {
            const disabledComponents = new Set();
            if (!treeData) return disabledComponents;
            function collect(node, ancestorDisabled) {
                if (!node) return;
                const nodeDisabled = ancestorDisabled || !!node.disabled;
                if (nodeDisabled && Array.isArray(node.components)) {
                    node.components.forEach(comp => disabledComponents.add(comp));
                }
                (node.children || []).forEach(child => {
                    const childDisabled = nodeDisabled || !!child.disabled;
                    collect(child.link_group, childDisabled);
                });
            }
            collect(treeData, !!treeData.disabled);
            return disabledComponents;
        }

        function toggleLinkActive(targetNode) {
            if (!targetNode || targetNode === treeData) return;
            saveState();
            const willDisable = !isLinkDisabled(targetNode);
            setSubtreeActive(targetNode, willDisable);
            syncIncomingJoint(treeData, targetNode, willDisable);
            if (!willDisable) {
                enableAncestors(treeData, targetNode);
            }

            if (willDisable) {
                if (viewerIsolatedNode && isLinkDisabled(viewerIsolatedNode)) {
                    viewerIsolatedNode = null;
                }
                const disabledComps = getDisabledComponents();
                if (viewerIsolatedComponent && disabledComps.has(viewerIsolatedComponent)) {
                    viewerIsolatedComponent = null;
                }
            }
            previewRigDirty = true;
            applyViewerIsolationVisibility();
            render();
            if (selectedElement) {
                updatePanel();
            }
        }

        function toggleJointActive(targetJoint) {
            if (!targetJoint) return;
            saveState();
            const willDisable = !isJointDisabled(targetJoint);
            targetJoint.disabled = willDisable;
            if (targetJoint.link_group) {
                setSubtreeActive(targetJoint.link_group, willDisable);
            }
            if (!willDisable) {
                enableJointAncestors(treeData, targetJoint);
            }
            if (willDisable) {
                if (viewerIsolatedNode && isLinkDisabled(viewerIsolatedNode)) {
                    viewerIsolatedNode = null;
                }
                const disabledComps = getDisabledComponents();
                if (viewerIsolatedComponent && disabledComps.has(viewerIsolatedComponent)) {
                    viewerIsolatedComponent = null;
                }
            }
            previewRigDirty = true;
            applyViewerIsolationVisibility();
            render();
            if (selectedElement) {
                updatePanel();
            }
        }

        function updateToggleActiveButtonUi(button, disabled, itemName = '') {
            if (!button) return;
            button.innerHTML = '<span class="toggle-knob"></span>';
            if (disabled) {
                button.classList.add('is-disabled');
                button.title = '비활성화 상태 (클릭하여 활성화 및 3D 모델 표시)';
                button.setAttribute('aria-label', `${itemName ? itemName + ' ' : ''}활성화`);
            } else {
                button.classList.remove('is-disabled');
                button.title = '활성화 상태 (클릭하여 비활성화 및 3D 모델 숨김)';
                button.setAttribute('aria-label', `${itemName ? itemName + ' ' : ''}비활성화`);
            }
        }

        function getLinkGroupColor(node) {
            if (!node || typeof node !== 'object') return 0x9ca3af;
            if (!linkColorAssignments.has(node)) {
                const colorIndex = nextLinkColorIndex++;
                let color = LINK_GROUP_COLORS[colorIndex];
                if (color === undefined) {
                    const generated = new THREE.Color();
                    generated.setHSL((colorIndex * 0.61803398875) % 1, 0.68, 0.56);
                    color = generated.getHex();
                }
                linkColorAssignments.set(node, color);
            }
            return linkColorAssignments.get(node);
        }

        function colorToCss(color) {
            return `#${Number(color).toString(16).padStart(6, '0')}`;
        }

        function getLinkGroupMaterial(color) {
            if (!linkGroupMaterials.has(color)) {
                linkGroupMaterials.set(color, new THREE.MeshPhongMaterial({
                    color,
                    side: THREE.DoubleSide,
                    flatShading: true,
                    shininess: 28
                }));
            }
            return linkGroupMaterials.get(color);
        }

        function attachMeshEdges(mesh, geometry, component) {
            if (!mesh || !geometry || meshEdgeDict[component]) return;
            const edgeLines = new THREE.LineSegments(
                new THREE.EdgesGeometry(geometry, 28),
                new THREE.LineBasicMaterial({
                    color: 0x121820,
                    transparent: true,
                    opacity: 0.48,
                    depthTest: true
                })
            );
            edgeLines.renderOrder = 2;
            mesh.add(edgeLines);
            meshEdgeDict[component] = edgeLines;
        }

        function processPendingMeshEdges() {
            meshEdgeBuildTimer = null;
            const batchSize = PETASOS_LOW_SPEC_RENDERING ? 1 : 4;
            for (let index = 0; index < batchSize && pendingMeshEdgeJobs.length; index++) {
                const job = pendingMeshEdgeJobs.shift();
                attachMeshEdges(job.mesh, job.geometry, job.component);
            }
            if (pendingMeshEdgeJobs.length) {
                meshEdgeBuildTimer = window.setTimeout(processPendingMeshEdges, 16);
            }
        }

        function scheduleMeshEdges(mesh, geometry, component) {
            if (!PETASOS_LOW_SPEC_RENDERING) {
                attachMeshEdges(mesh, geometry, component);
                return;
            }
            pendingMeshEdgeJobs.push({mesh, geometry, component});
            if (!meshEdgeBuildTimer) {
                meshEdgeBuildTimer = window.setTimeout(processPendingMeshEdges, 0);
            }
        }

        function applyLinkGroupColors() {
            if (!treeData) return;
            const assignedComponents = new Set();
            getFlatLinks(treeData, null, -1).forEach(item => {
                const color = getLinkGroupColor(item.node);
                const material = getLinkGroupMaterial(color);
                (item.node.components || []).forEach(component => {
                    assignedComponents.add(component);
                    const mesh = meshDict[component];
                    if (mesh) {
                        mesh.material = material;
                        mesh.userData.petasosLinkColor = color;
                    }
                    const edge = meshEdgeDict[component];
                    if (edge) {
                        edge.visible = true;
                        edge.material.opacity = 0.48;
                    }
                });
            });
            Object.entries(meshDict).forEach(([component, mesh]) => {
                if (!assignedComponents.has(component)) mesh.material = defaultMaterial;
            });
        }

        function refreshViewerColors() {
            if (viewerSelectedComponents.size > 0) {
                highlightViewerComponentSelection();
            } else if (selectedElement && selectedElement.node) {
                highlight3DComponents(selectedElement.node.components || []);
            } else {
                applyLinkGroupColors();
            }
        }

        /* JS Resize Logic */
        let isResizingH = false;
        let isResizingV = false;

        document.addEventListener('mousedown', (e) => {
            if (e.target.classList.contains('resizer-h')) isResizingH = true;
            if (e.target.classList.contains('resizer-v')) isResizingV = true;
            if (isResizingH || isResizingV) document.body.style.userSelect = 'none';
        });

        document.addEventListener('mousemove', (e) => {
            if (isResizingH) {
                const leftPane = document.querySelector('.left-pane');
                const previewPane = document.querySelector('.preview-pane');
                const totalHeight = leftPane.clientHeight;
                const newHeight = (e.clientY - leftPane.offsetTop) / totalHeight * 100;
                if (newHeight > 10 && newHeight < 90) {
                    previewPane.style.height = `${newHeight}%`;
                    onWindowResize(); // 3D 뷰어 크기 업데이트
                    scheduleTreeWireRender();
                }
            }
            if (isResizingV) {
                const editPane = document.querySelector('.edit-pane');
                const newWidth = window.innerWidth - e.clientX;
                if (newWidth >= 280 && newWidth < 800) {
                    editPane.style.width = `${newWidth}px`;
                    editPane.style.flexBasis = `${newWidth}px`;
                    onWindowResize(); // 3D 뷰어 크기 업데이트
                    scheduleTreeWireRender();
                }
            }
        });

        document.addEventListener('mouseup', () => {
            isResizingH = false;
            isResizingV = false;
            document.body.style.userSelect = 'auto';
        });

        let workspaceAutosaveTimer = null;
        let workspaceSaveInFlight = false;
        let workspaceAutosaveReady = false;
        let workspaceSaveFeedbackTimer = null;

        function workspaceEditorSettings() {
            return {
                fix_to_world: !!document.getElementById('fix-to-world')?.checked,
                root_joint_mode: rootJointMode(),
                export_mode: document.getElementById('export-mode')?.value || 'description',
            };
        }

        function setWorkspaceSaveButtonState(message, isError = false) {
            const button = document.getElementById('workspace-save-button');
            if (!button) return;
            if (workspaceSaveFeedbackTimer) {
                window.clearTimeout(workspaceSaveFeedbackTimer);
                workspaceSaveFeedbackTimer = null;
            }
            const isSaving = message === '저장 중...';
            const isSaved = message === '저장 완료';
            button.classList.toggle('is-saving', isSaving);
            button.classList.toggle('is-saved', isSaved);
            button.classList.toggle('is-save-error', !!isError);
            button.title = message;
            button.setAttribute('aria-label', message);
            if (isSaved || isError) {
                workspaceSaveFeedbackTimer = window.setTimeout(() => {
                    button.classList.remove('is-saving', 'is-saved', 'is-save-error');
                    button.setAttribute('aria-label', '현재 작업 저장');
                    updateWorkspaceManagerActiveState();
                    workspaceSaveFeedbackTimer = null;
                }, isError ? 3000 : 2400);
            }
        }

        async function saveWorkspace(showStatus = false, saveName = '') {
            if (
                !workspaceAutosaveReady
                || !treeData
                || !treeData._standalone
                || treeData._empty
            ) return false;
            if (workspaceSaveInFlight) {
                await new Promise(resolve => window.setTimeout(resolve, 120));
                return saveWorkspace(showStatus, saveName);
            }
            workspaceSaveInFlight = true;
            if (showStatus) setWorkspaceSaveButtonState('저장 중...');
            try {
                const response = await fetch('/workspace/save', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        tree: treeData,
                        editor_settings: workspaceEditorSettings(),
                        save_name: saveName,
                    }),
                });
                const result = await response.json();
                if (!response.ok) {
                    throw new Error(result.error || '작업 저장에 실패했습니다.');
                }
                const activeName = String(result.active_workspace_name || '').trim();
                if (activeName) {
                    treeData._active_workspace_name = activeName;
                    updateWorkspaceManagerActiveState();
                }
                if (showStatus) {
                    setWorkspaceSaveButtonState('저장 완료');
                }
                return result;
            } catch (error) {
                console.error('Workspace save failed:', error);
                setWorkspaceSaveButtonState('저장 실패', true);
                return false;
            } finally {
                workspaceSaveInFlight = false;
            }
        }

        function scheduleWorkspaceAutosave(delay = 700) {
            if (!workspaceAutosaveReady || !treeData || !treeData._standalone || treeData._empty) {
                return;
            }
            if (workspaceAutosaveTimer) clearTimeout(workspaceAutosaveTimer);
            workspaceAutosaveTimer = window.setTimeout(() => {
                workspaceAutosaveTimer = null;
                saveWorkspace(false);
            }, delay);
        }

        function setWorkspaceManagerStatus(message, isError = false) {
            const status = document.getElementById('workspace-manager-status');
            if (!status) return;
            status.style.display = 'block';
            status.classList.toggle('error', isError);
            status.textContent = message;
        }

        function activeWorkspaceName() {
            return String(treeData?._active_workspace_name || '').trim();
        }

        function closeHeaderWorkspaceMenu() {
            const menu = document.getElementById('header-workspace-menu');
            const button = document.getElementById('header-workspace-name');
            if (menu) menu.classList.remove('visible');
            if (button) button.setAttribute('aria-expanded', 'false');
        }

        async function refreshHeaderWorkspaceMenu() {
            const menu = document.getElementById('header-workspace-menu');
            if (!menu) return;
            menu.innerHTML = '<div class="header-workspace-menu-status">저장된 작업을 읽는 중...</div>';
            try {
                const response = await fetch('/workspace/list');
                const result = await response.json();
                if (!response.ok) {
                    throw new Error(result.error || '저장 작업 목록을 읽지 못했습니다.');
                }
                const items = Array.isArray(result.items) ? result.items : [];
                const activeName = activeWorkspaceName();
                menu.innerHTML = '';
                if (!items.length) {
                    menu.innerHTML = '<div class="header-workspace-menu-status">저장된 작업이 없습니다.</div>';
                    return;
                }
                items.forEach(item => {
                    const saveName = String(item.name || '').trim();
                    if (!saveName) return;
                    const option = document.createElement('button');
                    option.type = 'button';
                    option.className = `header-workspace-option${saveName === activeName ? ' active' : ''}`;
                    option.setAttribute('role', 'menuitem');
                    option.title = saveName;

                    const name = document.createElement('span');
                    name.className = 'header-workspace-option-name';
                    name.textContent = saveName;
                    option.appendChild(name);

                    if (saveName === activeName) {
                        const mark = document.createElement('span');
                        mark.className = 'header-workspace-option-mark';
                        mark.textContent = '현재';
                        option.appendChild(mark);
                    }
                    option.addEventListener('click', event => {
                        event.stopPropagation();
                        switchHeaderWorkspace(saveName);
                    });
                    menu.appendChild(option);
                });
            } catch (error) {
                menu.innerHTML = '';
                const status = document.createElement('div');
                status.className = 'header-workspace-menu-status error';
                status.textContent = error.message;
                menu.appendChild(status);
            }
        }

        function toggleHeaderWorkspaceMenu(event) {
            event?.stopPropagation();
            const menu = document.getElementById('header-workspace-menu');
            const button = document.getElementById('header-workspace-name');
            if (!menu || !button) return;
            const opening = !menu.classList.contains('visible');
            menu.classList.toggle('visible', opening);
            button.setAttribute('aria-expanded', opening ? 'true' : 'false');
            if (opening) refreshHeaderWorkspaceMenu();
        }

        async function switchHeaderWorkspace(saveName) {
            saveName = String(saveName || '').trim();
            if (!saveName) return;
            if (saveName === activeWorkspaceName()) {
                closeHeaderWorkspaceMenu();
                return;
            }
            if (!window.confirm(`'${saveName}' 작업으로 전환할까요?`)) return;
            workspaceAutosaveReady = false;
            if (workspaceAutosaveTimer) {
                clearTimeout(workspaceAutosaveTimer);
                workspaceAutosaveTimer = null;
            }
            const menu = document.getElementById('header-workspace-menu');
            if (menu) {
                menu.innerHTML = `<div class="header-workspace-menu-status">'${escapeHtmlText(saveName)}' 불러오는 중...</div>`;
            }
            try {
                const response = await fetch('/workspace/reload', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({save_name: saveName}),
                });
                const result = await response.json();
                if (!response.ok) {
                    throw new Error(result.error || '저장 작업을 불러오지 못했습니다.');
                }
                window.location.reload();
            } catch (error) {
                workspaceAutosaveReady = true;
                if (menu) {
                    menu.innerHTML = '';
                    const status = document.createElement('div');
                    status.className = 'header-workspace-menu-status error';
                    status.textContent = error.message;
                    menu.appendChild(status);
                }
            }
        }

        document.addEventListener('click', event => {
            if (!event.target.closest('.header-workspace-switcher')) {
                closeHeaderWorkspaceMenu();
            }
        });
        document.addEventListener('keydown', event => {
            if (event.key === 'Escape') closeHeaderWorkspaceMenu();
        });

        function updateWorkspaceManagerActiveState() {
            const activeName = activeWorkspaceName();
            const projectName = String(treeData?._project_name || '').trim();
            const displayName = activeName || projectName || '새 작업';
            const box = document.getElementById('workspace-active-save');
            const name = document.getElementById('workspace-active-name');
            const headerButton = document.getElementById('workspace-save-button');
            const headerName = document.getElementById('header-workspace-name');
            const headerValue = document.getElementById('header-workspace-value');
            if (box) box.style.display = activeName ? 'block' : 'none';
            if (name) name.textContent = activeName;
            if (headerName) {
                headerName.classList.toggle(
                    'visible',
                    !!treeData?._standalone && !treeData?._empty
                );
                headerName.title = activeName
                    ? `현재 저장 작업: ${activeName} · 클릭하여 다른 작업으로 전환`
                    : `현재 프로젝트: ${displayName} · 클릭하여 저장 작업 불러오기`;
                headerName.setAttribute(
                    'aria-label',
                    `현재 작업 ${displayName} · 저장 작업 선택`
                );
            }
            if (headerValue) headerValue.textContent = displayName;
            if (headerButton) {
                if (
                    !headerButton.classList.contains('is-saving')
                    && !headerButton.classList.contains('is-saved')
                    && !headerButton.classList.contains('is-save-error')
                ) {
                    headerButton.title = activeName
                        ? `저장 · 현재 작업: ${activeName}`
                        : '저장 · 현재 조립품 작업';
                }
            }
        }

        async function refreshWorkspaceList(preselectName = '') {
            const list = document.getElementById('workspace-saved-list');
            if (!list) return;
            list.innerHTML = '<option value="">저장 목록을 읽는 중...</option>';
            try {
                const response = await fetch('/workspace/list');
                const result = await response.json();
                if (!response.ok) throw new Error(result.error || '저장 목록을 읽지 못했습니다.');
                const items = Array.isArray(result.items) ? result.items : [];
                list.innerHTML = '';
                if (items.length) {
                    items.forEach(item => {
                        const date = Number.isFinite(Number(item.modified_at))
                            ? new Date(Number(item.modified_at) * 1000).toLocaleString()
                            : '';
                        const option = document.createElement('option');
                        option.value = item.name;
                        option.textContent = `${item.name}${date ? ` · ${date}` : ''}`;
                        list.appendChild(option);
                    });
                } else {
                    const option = document.createElement('option');
                    option.value = '';
                    option.textContent = '아직 이름을 붙여 저장한 작업이 없습니다.';
                    list.appendChild(option);
                }
                if (preselectName && items.some(item => item.name === preselectName)) {
                    list.value = preselectName;
                }
            } catch (error) {
                list.innerHTML = '<option value="">저장 목록 불러오기 실패</option>';
                setWorkspaceManagerStatus(error.message, true);
            }
        }

        function openWorkspaceManager(mode = 'save') {
            if (!treeData || !treeData._standalone || treeData._empty) return;
            const modal = document.getElementById('workspace-manager-modal');
            const status = document.getElementById('workspace-manager-status');
            if (status) {
                status.style.display = 'none';
                status.classList.remove('error');
                status.textContent = '';
            }
            updateWorkspaceManagerActiveState();
            if (modal) modal.style.display = 'flex';
            refreshWorkspaceList(activeWorkspaceName());
            window.setTimeout(() => {
                const target = mode === 'load'
                    ? document.getElementById('workspace-saved-list')
                    : (
                        mode !== 'save_as' && activeWorkspaceName()
                            ? document.getElementById('workspace-continue-save-button')
                            : document.getElementById('workspace-save-name')
                    );
                if (target) target.focus();
            }, 0);
        }

        function closeWorkspaceManager() {
            const modal = document.getElementById('workspace-manager-modal');
            if (modal) modal.style.display = 'none';
        }

        async function saveNamedWorkspace() {
            const input = document.getElementById('workspace-save-name');
            const saveName = String(input?.value || '').trim();
            if (!saveName) {
                setWorkspaceManagerStatus('저장 작업 이름을 입력하세요.', true);
                if (input) input.focus();
                return;
            }
            const list = document.getElementById('workspace-saved-list');
            const alreadyExists = Array.from(list?.options || []).some(
                option => option.value === saveName
            );
            if (
                alreadyExists
                && !window.confirm(`'${saveName}' 저장 작업을 현재 상태로 덮어쓸까요?`)
            ) return;
            setWorkspaceManagerStatus(`'${saveName}' 저장 중...`);
            const result = await saveWorkspace(true, saveName);
            if (!result) {
                setWorkspaceManagerStatus(`'${saveName}' 저장에 실패했습니다.`, true);
                return;
            }
            setWorkspaceManagerStatus(`'${result.save_name || saveName}' 작업을 저장했습니다.`);
            refreshWorkspaceList(result.save_name || saveName);
            updateWorkspaceManagerActiveState();
        }

        async function saveCurrentNamedWorkspace() {
            const saveName = activeWorkspaceName();
            if (!saveName) {
                setWorkspaceManagerStatus('먼저 새 저장 작업 이름을 만들어주세요.', true);
                return;
            }
            setWorkspaceManagerStatus(`'${saveName}'에 이어 저장하는 중...`);
            const result = await saveWorkspace(true, saveName);
            if (!result) {
                setWorkspaceManagerStatus(`'${saveName}' 이어 저장에 실패했습니다.`, true);
                return;
            }
            setWorkspaceManagerStatus(`'${saveName}'에 현재 작업을 이어 저장했습니다.`);
            refreshWorkspaceList(saveName);
            updateWorkspaceManagerActiveState();
        }

        async function saveActiveWorkspaceFromHeader() {
            const saveName = activeWorkspaceName();
            const result = await saveWorkspace(true, saveName);
            if (!result) return;
            updateWorkspaceManagerActiveState();
        }

        async function reloadNamedWorkspace() {
            if (!treeData || !treeData._standalone || treeData._empty) return;
            const list = document.getElementById('workspace-saved-list');
            const saveName = String(list?.value || '').trim();
            if (!saveName) {
                setWorkspaceManagerStatus('불러올 저장 작업을 목록에서 선택하세요.', true);
                return;
            }
            if (!window.confirm(`'${saveName}' 작업을 불러올까요? 현재 화면은 선택한 저장 상태로 바뀝니다.`)) return;
            workspaceAutosaveReady = false;
            if (workspaceAutosaveTimer) {
                clearTimeout(workspaceAutosaveTimer);
                workspaceAutosaveTimer = null;
            }
            setWorkspaceManagerStatus(`'${saveName}' 불러오는 중...`);
            try {
                const response = await fetch('/workspace/reload', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({save_name: saveName}),
                });
                const result = await response.json();
                if (!response.ok) {
                    throw new Error(result.error || '저장 작업을 불러오지 못했습니다.');
                }
                window.location.reload();
            } catch (error) {
                workspaceAutosaveReady = true;
                setWorkspaceManagerStatus(error.message, true);
            }
        }

        fetch('/data').then(r => r.json()).then(data => {
            treeData = data;
            if (treeData._standalone) {
                const importButton = document.getElementById('standalone-import-button');
                if (importButton) importButton.style.display = '';
                const reimportButton = document.getElementById('standalone-reimport-button');
                if (reimportButton) reimportButton.style.display = treeData._empty ? 'none' : '';
                const workspaceSaveButton = document.getElementById('workspace-save-button');
                if (workspaceSaveButton) workspaceSaveButton.style.display = '';
                const workspaceSaveAsButton = document.getElementById('workspace-save-as-button');
                if (workspaceSaveAsButton) workspaceSaveAsButton.style.display = '';
                updateWorkspaceManagerActiveState();
                const projectNameInput = document.getElementById('standalone-project-name');
                if (projectNameInput && treeData._project_name) {
                    projectNameInput.value = treeData._project_name;
                }
                const editorSettings = treeData._editor_settings || {};
                const fixToWorld = document.getElementById('fix-to-world');
                const rootJointModeInput = document.getElementById('root-joint-mode');
                const restoredRootMode = ['world', 'base_footprint', 'none'].includes(
                    editorSettings.root_joint_mode
                )
                    ? editorSettings.root_joint_mode
                    : (editorSettings.fix_to_world === false ? 'none' : 'world');
                if (rootJointModeInput) rootJointModeInput.value = restoredRootMode;
                if (fixToWorld) {
                    fixToWorld.checked = restoredRootMode === 'world';
                }
                if (restoredRootMode === 'base_footprint' && !treeData._base_footprint_frame) {
                    treeData._base_footprint_frame = { world_xyz: [0, 0, 0], rpy: [0, 0, 0], yaw: 0 };
                }
                const exportMode = document.getElementById('export-mode');
                if (exportMode && editorSettings.export_mode === 'moveit') {
                    exportMode.value = 'moveit';
                }
                workspaceAutosaveReady = !treeData._empty;
                if (treeData._empty) {
                    setTimeout(openStandaloneImport, 150);
                }
            }
            render();
            try {
                init3D(); // 데이터 로드 후 3D 초기화
            } catch (error) {
                console.error('3D preview initialization failed:', error);
                const viewerStatus = document.getElementById('viewer-status');
                if (viewerStatus) {
                    viewerStatus.classList.add('error');
                    viewerStatus.innerText = '3D preview failed to initialize. Robot tree is still available.';
                }
            }
        });

        function setStandaloneImportMode(mode) {
            const workspaceMode = mode === 'workspace';
            const cadPanel = document.getElementById('standalone-cad-import-panel');
            const workspacePanel = document.getElementById('standalone-workspace-load-panel');
            const cadTab = document.getElementById('import-mode-cad');
            const workspaceTab = document.getElementById('import-mode-workspace');
            if (cadPanel) cadPanel.style.display = workspaceMode ? 'none' : 'block';
            if (workspacePanel) workspacePanel.style.display = workspaceMode ? 'block' : 'none';
            if (cadTab) cadTab.classList.toggle('active', !workspaceMode);
            if (workspaceTab) workspaceTab.classList.toggle('active', workspaceMode);
            if (workspaceMode) refreshStandaloneWorkspaceList();
        }

        function setStandaloneWorkspaceStatus(message, isError = false) {
            const status = document.getElementById('standalone-workspace-status');
            if (!status) return;
            status.style.display = message ? 'block' : 'none';
            status.classList.toggle('error', isError);
            status.textContent = message || '';
        }

        async function refreshStandaloneWorkspaceList() {
            const list = document.getElementById('standalone-workspace-list');
            if (!list) return;
            list.innerHTML = '<option value="">저장 목록을 읽는 중...</option>';
            setStandaloneWorkspaceStatus('');
            try {
                const response = await fetch('/workspace/list?all_projects=1');
                const result = await response.json();
                if (!response.ok) throw new Error(result.error || '이전 작업 목록을 읽지 못했습니다.');
                const items = Array.isArray(result.items) ? result.items : [];
                list.innerHTML = '';
                if (!items.length) {
                    const option = document.createElement('option');
                    option.value = '';
                    option.textContent = '아직 이름을 붙여 저장한 작업이 없습니다.';
                    list.appendChild(option);
                    return;
                }
                items.forEach((item, index) => {
                    const date = Number.isFinite(Number(item.modified_at))
                        ? new Date(Number(item.modified_at) * 1000).toLocaleString()
                        : '';
                    const option = document.createElement('option');
                    option.value = String(index);
                    option.dataset.projectId = String(item.project_id || '');
                    option.dataset.saveName = String(item.name || '');
                    option.textContent = `${item.project_name || item.project_id} / ${item.name}${date ? ` · ${date}` : ''}`;
                    list.appendChild(option);
                });
                list.selectedIndex = 0;
            } catch (error) {
                list.innerHTML = '<option value="">이전 작업 목록 불러오기 실패</option>';
                setStandaloneWorkspaceStatus(error.message, true);
            }
        }

        async function loadStandaloneWorkspace() {
            const list = document.getElementById('standalone-workspace-list');
            const option = list?.selectedOptions?.[0];
            const projectId = String(option?.dataset.projectId || '').trim();
            const saveName = String(option?.dataset.saveName || '').trim();
            if (!projectId || !saveName) {
                setStandaloneWorkspaceStatus('불러올 이전 작업을 선택하세요.', true);
                return;
            }
            if (!window.confirm(`'${saveName}' 작업을 불러올까요? 현재 화면은 선택한 저장 상태로 바뀝니다.`)) return;
            workspaceAutosaveReady = false;
            if (workspaceAutosaveTimer) {
                clearTimeout(workspaceAutosaveTimer);
                workspaceAutosaveTimer = null;
            }
            setStandaloneWorkspaceStatus(`'${saveName}' 불러오는 중...`);
            try {
                const response = await fetch('/workspace/reload', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        project_id: projectId,
                        save_name: saveName,
                    }),
                });
                const result = await response.json();
                if (!response.ok) {
                    throw new Error(result.error || '이전 작업을 불러오지 못했습니다.');
                }
                window.location.reload();
            } catch (error) {
                workspaceAutosaveReady = true;
                setStandaloneWorkspaceStatus(error.message, true);
            }
        }

        let standaloneImportIntent = 'new';

        function configureStandaloneImportIntent(intent) {
            standaloneImportIntent = intent === 'update' ? 'update' : 'new';
            const updating = standaloneImportIntent === 'update';
            const title = document.getElementById('standalone-import-title');
            const note = document.getElementById('standalone-reimport-note');
            const submit = document.getElementById('standalone-import-submit');
            const projectName = document.getElementById('standalone-project-name');
            const inventorDirect = document.getElementById('standalone-inventor-direct');
            const inventorDirectTitle = document.getElementById('standalone-inventor-direct-title');
            const tabs = document.querySelector('#standalone-import-modal .import-mode-tabs');
            if (title) title.textContent = updating ? 'CAD 업데이트' : '불러오기';
            if (note) note.style.display = updating ? 'block' : 'none';
            if (submit) submit.textContent = updating ? '업데이트 적용' : '가져오기';
            if (projectName) projectName.readOnly = updating;
            if (inventorDirect) inventorDirect.style.display = 'block';
            if (inventorDirectTitle) inventorDirectTitle.textContent = updating
                ? '기존 편집을 유지하는 Inventor 직접 업데이트'
                : 'IPT를 따로 선택하지 않는 Inventor 직접 연결';
            if (tabs) tabs.style.display = updating ? 'none' : '';
        }

        function openStandaloneImport() {
            configureStandaloneImportIntent('new');
            const modal = document.getElementById('standalone-import-modal');
            const status = document.getElementById('standalone-import-status');
            if (status) {
                status.style.display = 'none';
                status.classList.remove('error');
                status.innerText = '';
            }
            setStandaloneImportMode('cad');
            if (modal) modal.style.display = 'flex';
        }

        function openStandaloneReimport() {
            if (!treeData || treeData._empty) return;
            configureStandaloneImportIntent('update');
            const modal = document.getElementById('standalone-import-modal');
            const status = document.getElementById('standalone-import-status');
            const projectName = document.getElementById('standalone-project-name');
            if (projectName) projectName.value = treeData._project_name || projectName.value;
            if (status) {
                status.style.display = 'none';
                status.classList.remove('error');
                status.innerText = '';
            }
            setStandaloneImportMode('cad');
            if (modal) modal.style.display = 'flex';
        }

        function closeStandaloneImport() {
            const modal = document.getElementById('standalone-import-modal');
            if (modal) modal.style.display = 'none';
        }

        async function importDirectInventor(endpoint) {
            const projectName = document.getElementById('standalone-project-name').value.trim();
            const status = document.getElementById('standalone-import-status');
            const updating = standaloneImportIntent === 'update';
            const requestEndpoint = updating
                ? endpoint.replace('/import/', '/reimport/')
                : endpoint;
            if (!projectName) {
                status.style.display = 'block';
                status.classList.add('error');
                status.innerText = '프로젝트 이름을 입력하세요.';
                return;
            }
            if (updating && !window.confirm(
                '현재 링크 그룹과 조인트 편집을 유지하면서 Inventor 조립품으로 업데이트할까요?'
            )) return;
            status.style.display = 'block';
            status.classList.remove('error');
            status.innerText = endpoint.endsWith('active')
                ? (updating
                    ? '현재 Inventor 조립품을 읽고 기존 편집과 비교하고 있습니다...'
                    : '현재 Inventor 조립품과 참조 부품을 읽고 있습니다...')
                : (updating
                    ? '업데이트할 원본 IAM을 선택하세요. 기존 편집과 비교하여 병합합니다...'
                    : 'Windows 파일 선택창에서 원본 IAM을 선택하세요...');
            try {
                const response = await fetch(requestEndpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        project_name: projectName,
                        tree: updating ? treeData : undefined,
                    })
                });
                const result = await response.json();
                if (!response.ok) throw new Error(result.error || 'Inventor 가져오기에 실패했습니다.');
                if (result.status === 'cancelled') {
                    status.innerText = '원본 IAM 선택을 취소했습니다.';
                    return;
                }
                status.innerText = updating
                    ? `Inventor 직접 업데이트 완료 · ${result.reimport?.matched_parts || 0}개 부품의 링크·조인트 편집을 유지했습니다.`
                    : `${result.report.parts}개 부품과 ${result.report.joints}개 조인트를 Inventor에서 가져왔습니다.`;
                window.location.reload();
            } catch (error) {
                status.classList.add('error');
                status.innerText = error.message;
            }
        }

        async function importStandaloneAssembly() {
            const files = document.getElementById('standalone-files').files;
            const folderFiles = document.getElementById('standalone-folder').files;
            const projectName = document.getElementById('standalone-project-name').value.trim();
            const status = document.getElementById('standalone-import-status');
            const selectedCount = (files ? files.length : 0) + (folderFiles ? folderFiles.length : 0);
            const updating = standaloneImportIntent === 'update';
            if (!projectName || selectedCount === 0) {
                status.style.display = 'block';
                status.classList.add('error');
                status.innerText = '프로젝트 이름과 조립품 파일 또는 프로젝트 폴더가 필요합니다.';
                return;
            }
            if (updating && !window.confirm(
                '현재 링크 그룹과 조인트 편집을 유지하면서 선택한 CAD로 형상을 업데이트할까요?'
            )) return;
            const allSelectedFiles = [
                ...Array.from(files || []),
                ...Array.from(folderFiles || [])
            ];
            const selectedNames = allSelectedFiles.map(file => file.name.toLowerCase());
            const hasIam = selectedNames.some(name => name.endsWith('.iam'));
            const hasInventorDependency = selectedNames.some(name =>
                name.endsWith('.ipt') || (name.endsWith('.iam') && selectedNames.filter(item => item.endsWith('.iam')).length > 1)
            );
            if (hasIam && !hasInventorDependency) {
                status.style.display = 'block';
                status.classList.add('error');
                status.innerText = 'IAM은 형상을 내장하지 않습니다. 아래 폴더 선택에서 IAM과 참조 IPT가 함께 있는 프로젝트 폴더 전체를 선택하세요.';
                return;
            }
            status.style.display = 'block';
            status.classList.remove('error');
            status.innerText = updating
                ? '업데이트된 부품을 기존 편집 작업과 비교하고 있습니다...'
                : '형상과 조립 정보를 분석하고 있습니다...';
            const form = new FormData();
            form.append('project_name', projectName);
            Array.from(files).forEach(file => form.append('files', file));
            Array.from(folderFiles).forEach(file => {
                form.append('relative_files', file, file.webkitRelativePath || file.name);
            });
            if (updating) form.append('tree', JSON.stringify(treeData));
            try {
                const response = await fetch(updating ? '/reimport' : '/import', { method: 'POST', body: form });
                const result = await response.json();
                if (!response.ok) throw new Error(
                    result.error || (updating ? 'CAD 업데이트에 실패했습니다.' : '가져오기에 실패했습니다.')
                );
                if (updating) {
                    const changedCount = Array.isArray(result.reimport?.changed_parts)
                        ? result.reimport.changed_parts.length
                        : 0;
                    status.innerText = `CAD 업데이트 완료 · ${result.reimport?.matched_parts || 0}개 부품의 편집을 유지하고 ${changedCount}개 변경을 반영했습니다.`;
                } else {
                    status.innerText = `${result.report.parts}개 부품과 ${result.report.joints}개 조인트를 가져왔습니다.`;
                }
                window.location.reload();
            } catch (error) {
                status.classList.add('error');
                status.innerText = error.message;
            }
        }

        function resolvePreviewUpAxis() {
            const declared = String((treeData && treeData._preview_up_axis) || '').toLowerCase();
            if (['x', 'y', 'z'].includes(declared)) return declared;
            const source = String(
                (treeData && treeData._import_report && treeData._import_report.source_application) || ''
            ).toLowerCase();
            return source.includes('inventor') ? 'y' : 'z';
        }

        function applyRobotRootUpAxis(axis) {
            if (!robotRoot) return;
            robotRoot.position.set(0, 0, 0);
            robotRoot.rotation.set(0, 0, 0);
            if (axis === 'z') {
                robotRoot.rotation.x = -Math.PI / 2;
            } else if (axis === 'x') {
                robotRoot.rotation.z = Math.PI / 2;
            }
            robotRoot.updateMatrixWorld(true);
        }

        function applyStoredRobotRootTransform() {
            if (!robotRoot || !treeData) return false;
            const quaternion = treeData._preview_root_quaternion;
            const position = treeData._preview_root_position;
            if (!Array.isArray(quaternion) || quaternion.length !== 4) return false;
            if (!quaternion.every(Number.isFinite)) return false;
            robotRoot.quaternion.fromArray(quaternion).normalize();
            if (Array.isArray(position) && position.length === 3 && position.every(Number.isFinite)) {
                robotRoot.position.fromArray(position);
            } else {
                robotRoot.position.set(0, 0, 0);
            }
            robotRoot.updateMatrixWorld(true);
            return true;
        }

        function syncPreviewRootTransform() {
            if (!treeData || !robotRoot) return;
            const rosFrame = new THREE.Quaternion().setFromEuler(
                new THREE.Euler(Math.PI / 2, 0, 0, 'XYZ')
            );
            const rosQuaternion = rosFrame.clone().multiply(robotRoot.quaternion).normalize();
            const rosRotation = new THREE.Matrix4().makeRotationFromQuaternion(rosQuaternion);
            const rotation = rosRotation.elements;
            const pitch = Math.atan2(
                -rotation[2],
                Math.hypot(rotation[0], rotation[1])
            );
            let roll;
            let yaw;
            if (Math.abs(Math.abs(pitch) - Math.PI / 2) < 1e-9) {
                roll = Math.atan2(-rotation[9], rotation[5]);
                yaw = 0;
            } else {
                roll = Math.atan2(rotation[6], rotation[10]);
                yaw = Math.atan2(rotation[1], rotation[0]);
            }
            const unitsPerMeter = Number(treeData._preview_units_per_meter) || 1000.0;
            const rosPosition = robotRoot.position.clone().applyQuaternion(rosFrame).divideScalar(unitsPerMeter);
            treeData._preview_root_quaternion = robotRoot.quaternion.toArray();
            treeData._preview_root_position = robotRoot.position.toArray();
            treeData._preview_root_rpy = [roll, pitch, yaw];
            treeData._preview_root_xyz = rosPosition.toArray();
        }

        function clearCustomGroundTransform() {
            if (!treeData) return;
            delete treeData._preview_root_quaternion;
            delete treeData._preview_root_position;
            delete treeData._preview_root_rpy;
            delete treeData._preview_root_xyz;
            delete treeData._preview_ground_face;
        }

        function repairStoredGroundTransformIfBelowPlane() {
            const ground = treeData?._preview_ground_face;
            if (!ground || !robotRoot) return false;
            const component = String(ground.component || '');
            const anchorValues = ground.center_local;
            const anchorMesh = meshDict[component];
            if (
                !anchorMesh
                || !Array.isArray(anchorValues)
                || anchorValues.length !== 3
                || !anchorValues.every(Number.isFinite)
            ) return false;

            const anchorLocal = new THREE.Vector3().fromArray(anchorValues);
            const anchorGeometry = anchorMesh.geometry;
            if (anchorGeometry && !anchorGeometry.boundingBox) {
                anchorGeometry.computeBoundingBox();
            }
            if (anchorGeometry?.boundingBox) {
                const anchorSize = new THREE.Vector3();
                anchorGeometry.boundingBox.getSize(anchorSize);
                const anchorDiagonal = Math.max(anchorSize.length(), 1);
                const anchorDistance = anchorGeometry.boundingBox.distanceToPoint(anchorLocal);
                const circleRadius = Number(ground.circle_radius || 0);
                const invalidStoredSnap = (
                    anchorDistance > anchorDiagonal * 8
                    || (circleRadius > 0 && circleRadius > anchorDiagonal * 8)
                );
                if (invalidStoredSnap) {
                    clearCustomGroundTransform();
                    applyRobotRootUpAxis(resolvePreviewUpAxis());
                    updateGroundFaceUi('비정상적으로 멀리 저장된 원점을 해제했습니다. 바닥면을 다시 지정하세요.');
                    return true;
                }
            }

            const box = new THREE.Box3();
            Object.values(meshDict).forEach(mesh => box.expandByObject(mesh));
            if (box.isEmpty()) return false;
            const size = new THREE.Vector3();
            const center = new THREE.Vector3();
            box.getSize(size);
            box.getCenter(center);
            const tolerance = Math.max(size.y * 0.0001, 0.0001);
            if (center.y >= -tolerance) return false;

            const flipAroundWorldX = new THREE.Quaternion().setFromAxisAngle(
                new THREE.Vector3(1, 0, 0),
                Math.PI
            );
            robotRoot.quaternion.premultiply(flipAroundWorldX).normalize();
            robotRoot.updateMatrixWorld(true);
            const anchorWorld = anchorMesh.localToWorld(
                new THREE.Vector3().fromArray(anchorValues)
            );
            robotRoot.position.sub(anchorWorld);
            robotRoot.updateMatrixWorld(true);
            ground.normal_flipped_to_keep_model_above = true;
            ground.repaired_after_load = true;
            syncPreviewRootTransform();
            return true;
        }

        function groundSnapMarkerRadius() {
            const box = new THREE.Box3();
            Object.values(meshDict).forEach(mesh => box.expandByObject(mesh));
            if (box.isEmpty()) return 12;
            const size = new THREE.Vector3();
            box.getSize(size);
            return Math.max(4, Math.min(45, size.length() * 0.018));
        }

        function ensureGroundSnapMarker() {
            if (groundSnapMarker || !scene) return groundSnapMarker;
            const material = new THREE.MeshBasicMaterial({
                color: 0xffd54f,
                transparent: true,
                opacity: 0.95,
                // Keep the marker from showing through the opposite side of the
                // model.  It used to ignore the depth buffer, which made the
                // ground-selection ring look as if it entered the solid.
                depthTest: true,
                depthWrite: false,
                side: THREE.DoubleSide,
            });
            groundSnapMarker = new THREE.Group();
            groundSnapMarker.name = 'petasos-ground-origin-snap';
            const ring = new THREE.Mesh(
                new THREE.TorusGeometry(1, 0.085, 10, 40),
                material
            );
            const center = new THREE.Mesh(
                new THREE.SphereGeometry(0.22, 16, 12),
                material
            );
            ring.renderOrder = 900;
            center.renderOrder = 901;
            groundSnapMarker.add(ring, center);
            groundSnapMarker.visible = false;
            scene.add(groundSnapMarker);
            return groundSnapMarker;
        }

        function showGroundSnapMarker(
            worldPoint,
            worldNormal,
            isOrigin = false,
            exactRadius = null
        ) {
            const marker = ensureGroundSnapMarker();
            if (!marker || !worldPoint) return;
            if (marker.parent !== scene) scene.add(marker);
            const normal = worldNormal && worldNormal.lengthSq() > 0.5
                ? worldNormal.clone().normalize()
                : new THREE.Vector3(0, 1, 0);
            const markerRadius = Number(exactRadius) > 0
                ? Number(exactRadius)
                : groundSnapMarkerRadius();
            // The torus has a tube radius of 0.085. Lift it by roughly that
            // amount so it rests on the selected surface instead of intersecting
            // it, while depth testing still hides portions occluded by geometry.
            const surfaceOffset = Math.max(0.002, markerRadius * 0.09);
            marker.position.copy(worldPoint).addScaledVector(normal, surfaceOffset);
            marker.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), normal);
            marker.scale.setScalar(markerRadius);
            marker.traverse(child => {
                if (child.material && child.material.color) {
                    child.material.color.setHex(isOrigin ? 0x66ff88 : 0xffd54f);
                }
            });
            marker.visible = true;
        }

        function hideGroundSnapMarker() {
            if (groundSnapMarker) groundSnapMarker.visible = false;
        }

        function ensureJointSnapMarker() {
            if (jointSnapMarker || !scene) return jointSnapMarker;

            const overlayMaterial = (color, opacity = 1) => new THREE.MeshBasicMaterial({
                color,
                transparent: opacity < 1,
                opacity,
                depthTest: false,
                depthWrite: false,
                side: THREE.DoubleSide,
            });
            const lineMaterial = (color, opacity = 1) => new THREE.LineBasicMaterial({
                color,
                transparent: opacity < 1,
                opacity,
                depthTest: false,
                depthWrite: false,
            });

            jointSnapMarker = new THREE.Group();
            jointSnapMarker.name = 'petasos-joint-snap-marker';

            const haloMaterial = overlayMaterial(0x35e7ff, 0.96);
            const centerMaterial = overlayMaterial(0xffffff, 1);
            const normalMaterial = overlayMaterial(0x4d9cff, 1);
            const backNormalMaterial = overlayMaterial(0x7db7ff, 0.72);
            jointSnapMarker.userData.haloMaterial = haloMaterial;
            jointSnapMarker.userData.centerMaterial = centerMaterial;

            const innerRing = new THREE.Mesh(
                new THREE.TorusGeometry(0.72, 0.075, 12, 56),
                haloMaterial
            );
            innerRing.name = 'joint-snap-inner-ring';
            const outerRing = new THREE.Mesh(
                new THREE.TorusGeometry(1, 0.035, 10, 64),
                haloMaterial
            );
            outerRing.name = 'joint-snap-feature-ring';
            jointSnapMarker.userData.outerRing = outerRing;

            const center = new THREE.Mesh(
                new THREE.SphereGeometry(0.18, 18, 14),
                centerMaterial
            );
            center.name = 'joint-snap-center';

            const crossGeometry = new THREE.BufferGeometry().setFromPoints([
                new THREE.Vector3(-1.18, 0, 0), new THREE.Vector3(1.18, 0, 0),
                new THREE.Vector3(0, -1.18, 0), new THREE.Vector3(0, 1.18, 0),
            ]);
            const cross = new THREE.LineSegments(crossGeometry, lineMaterial(0x9af4ff, 0.9));
            cross.name = 'joint-snap-plane-crosshair';

            const addNormalArrow = (direction, material, name) => {
                const shaft = new THREE.Mesh(
                    new THREE.CylinderGeometry(0.045, 0.045, 1.12, 12),
                    material
                );
                shaft.position.z = direction * 0.56;
                shaft.rotation.x = Math.PI / 2;
                const cone = new THREE.Mesh(
                    new THREE.ConeGeometry(0.14, 0.34, 16),
                    material
                );
                cone.position.z = direction * 1.24;
                cone.rotation.x = direction > 0 ? Math.PI / 2 : -Math.PI / 2;
                shaft.name = `${name}-shaft`;
                cone.name = `${name}-head`;
                jointSnapMarker.add(shaft, cone);
            };
            addNormalArrow(1, normalMaterial, 'joint-snap-axis-forward');
            addNormalArrow(-1, backNormalMaterial, 'joint-snap-axis-backward');

            [innerRing, outerRing, center, cross].forEach((item, index) => {
                item.renderOrder = 1100 + index;
                jointSnapMarker.add(item);
            });
            jointSnapMarker.traverse(child => {
                child.renderOrder = Math.max(Number(child.renderOrder) || 0, 1100);
            });
            jointSnapMarker.visible = false;
            scene.add(jointSnapMarker);
            return jointSnapMarker;
        }

        function showJointSnapMarker(
            worldPoint,
            worldNormal,
            exactRadius = null,
            selected = false
        ) {
            const marker = ensureJointSnapMarker();
            if (!marker || !worldPoint) return;
            if (marker.parent !== scene) scene.add(marker);
            const normal = worldNormal && worldNormal.lengthSq() > 0.5
                ? worldNormal.clone().normalize()
                : new THREE.Vector3(0, 1, 0);
            const baseRadius = groundSnapMarkerRadius();
            const featureRadius = Number(exactRadius) > 0
                ? Math.max(baseRadius * 0.9, Math.min(baseRadius * 2.4, Number(exactRadius)))
                : baseRadius;
            marker.position.copy(worldPoint).addScaledVector(normal, baseRadius * 0.025);
            marker.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), normal);
            marker.scale.setScalar(baseRadius);
            const outerRing = marker.userData.outerRing;
            if (outerRing) outerRing.scale.setScalar(featureRadius / baseRadius);
            marker.userData.haloMaterial.color.setHex(selected ? 0x66ff88 : 0x35e7ff);
            marker.userData.centerMaterial.color.setHex(selected ? 0xeaffee : 0xffffff);
            marker.visible = true;
        }

        function hideJointSnapMarker() {
            if (jointSnapMarker) jointSnapMarker.visible = false;
        }

        function ensureBaseFootprintFrameMarker() {
            if (baseFootprintFrameMarker || !scene) return baseFootprintFrameMarker;
            baseFootprintFrameMarker = new THREE.Group();
            baseFootprintFrameMarker.name = 'petasos-base-footprint-frame';

            const plane = new THREE.GridHelper(2, 4, 0x50e3a4, 0x287c66);
            plane.name = 'base-footprint-plane';
            const planeMaterials = Array.isArray(plane.material) ? plane.material : [plane.material];
            planeMaterials.forEach(material => {
                material.transparent = true;
                material.opacity = 0.82;
                material.depthTest = false;
                material.depthWrite = false;
            });
            plane.renderOrder = 1050;
            baseFootprintFrameMarker.add(plane);

            const ring = new THREE.Mesh(
                new THREE.TorusGeometry(0.38, 0.035, 10, 48),
                new THREE.MeshBasicMaterial({
                    color: 0x5bffb0,
                    transparent: true,
                    opacity: 0.95,
                    depthTest: false,
                    depthWrite: false,
                })
            );
            ring.rotation.x = Math.PI / 2;
            ring.name = 'base-footprint-center-ring';
            baseFootprintFrameMarker.add(ring);

            const axes = [
                { direction: new THREE.Vector3(1, 0, 0), color: 0xff4d4d },
                { direction: new THREE.Vector3(0, 0, -1), color: 0x55dd77 },
                { direction: new THREE.Vector3(0, 1, 0), color: 0x4d8dff },
            ];
            axes.forEach(({ direction, color }) => {
                const arrow = new THREE.ArrowHelper(direction, new THREE.Vector3(), 1, color, 0.18, 0.09);
                arrow.name = 'base-footprint-axis';
                arrow.line.material.depthTest = false;
                arrow.line.material.depthWrite = false;
                arrow.cone.material.depthTest = false;
                arrow.cone.material.depthWrite = false;
                arrow.line.renderOrder = 1052;
                arrow.cone.renderOrder = 1053;
                baseFootprintFrameMarker.add(arrow);
            });

            const makeAxisLabel = (text, color, position) => {
                const canvas = document.createElement('canvas');
                canvas.width = 128;
                canvas.height = 128;
                const context = canvas.getContext('2d');
                context.clearRect(0, 0, canvas.width, canvas.height);
                context.beginPath();
                context.arc(64, 64, 43, 0, Math.PI * 2);
                context.fillStyle = 'rgba(10, 18, 22, 0.88)';
                context.fill();
                context.lineWidth = 8;
                context.strokeStyle = color;
                context.stroke();
                context.fillStyle = '#ffffff';
                context.font = 'bold 58px sans-serif';
                context.textAlign = 'center';
                context.textBaseline = 'middle';
                context.fillText(text, 64, 67);
                const texture = new THREE.CanvasTexture(canvas);
                texture.minFilter = THREE.LinearFilter;
                const material = new THREE.SpriteMaterial({
                    map: texture,
                    transparent: true,
                    depthTest: false,
                    depthWrite: false,
                });
                const sprite = new THREE.Sprite(material);
                sprite.name = `base-footprint-axis-label-${text.toLowerCase()}`;
                sprite.position.copy(position);
                sprite.scale.set(0.42, 0.42, 0.42);
                sprite.renderOrder = 1060;
                baseFootprintFrameMarker.add(sprite);
            };
            makeAxisLabel('X', '#ff4d4d', new THREE.Vector3(1.24, 0, 0));
            makeAxisLabel('Y', '#55dd77', new THREE.Vector3(0, 0, -1.24));
            makeAxisLabel('Z', '#4d8dff', new THREE.Vector3(0, 1.24, 0));

            baseFootprintFrameMarker.visible = false;
            scene.add(baseFootprintFrameMarker);
            return baseFootprintFrameMarker;
        }

        function showBaseFootprintFrameMarker() {
            const marker = ensureBaseFootprintFrameMarker();
            const frame = treeData?._base_footprint_frame;
            if (
                !marker
                || !frame
                || rootJointMode() !== 'base_footprint'
                || (!baseFootprintFrameSelected && !baseFootprintPickMode)
            ) {
                if (marker) marker.visible = false;
                return;
            }
            const xyz = Array.isArray(frame.world_xyz) && frame.world_xyz.length === 3
                ? frame.world_xyz.map(value => Number(value) || 0)
                : [0, 0, 0];
            const markerSize = Math.max(12, groundSnapMarkerRadius() * 3.2);
            marker.position.copy(rosOffsetMetersToViewer(xyz));
            const rpy = Array.isArray(frame.rpy) && frame.rpy.length === 3
                ? frame.rpy.map(value => Number(value) || 0)
                : [0, 0, Number(frame.yaw) || 0];
            const rosRotation = new THREE.Matrix4().makeRotationFromEuler(
                new THREE.Euler(rpy[0], rpy[1], rpy[2], 'ZYX')
            );
            const rosToViewerDirection = vector => new THREE.Vector3(
                vector.x,
                vector.z,
                -vector.y
            );
            const viewerXAxis = rosToViewerDirection(
                new THREE.Vector3(1, 0, 0).applyMatrix4(rosRotation)
            ).normalize();
            const viewerYAxis = rosToViewerDirection(
                new THREE.Vector3(0, 0, 1).applyMatrix4(rosRotation)
            ).normalize();
            const viewerZAxis = rosToViewerDirection(
                new THREE.Vector3(0, -1, 0).applyMatrix4(rosRotation)
            ).normalize();
            marker.quaternion.setFromRotationMatrix(
                new THREE.Matrix4().makeBasis(viewerXAxis, viewerYAxis, viewerZAxis)
            );
            marker.scale.setScalar(markerSize);
            marker.visible = true;
        }

        function attachJointSnapMarkerToRig() {
            if (!activeJointSnapMarkerInfo) return;
            const controller = previewJointControllers.find(
                item => item.jointInfo === activeJointSnapMarkerInfo
            );
            const marker = ensureJointSnapMarker();
            if (!controller || !marker) return;
            controller.pivot.add(marker);
            marker.position.set(0, 0, 0);
            marker.quaternion.identity();
            marker.scale.setScalar(groundSnapMarkerRadius());
            if (marker.userData.outerRing) marker.userData.outerRing.scale.setScalar(1);
            marker.userData.haloMaterial.color.setHex(0x66ff88);
            marker.userData.centerMaterial.color.setHex(0xeaffee);
            marker.visible = true;
        }

        function solveLinear3(matrix, vector) {
            const rows = matrix.map((row, index) => [...row, vector[index]]);
            for (let column = 0; column < 3; column += 1) {
                let pivot = column;
                for (let row = column + 1; row < 3; row += 1) {
                    if (Math.abs(rows[row][column]) > Math.abs(rows[pivot][column])) {
                        pivot = row;
                    }
                }
                if (Math.abs(rows[pivot][column]) < 1e-12) return null;
                [rows[column], rows[pivot]] = [rows[pivot], rows[column]];
                const divisor = rows[column][column];
                for (let item = column; item < 4; item += 1) rows[column][item] /= divisor;
                for (let row = 0; row < 3; row += 1) {
                    if (row === column) continue;
                    const factor = rows[row][column];
                    for (let item = column; item < 4; item += 1) {
                        rows[row][item] -= factor * rows[column][item];
                    }
                }
            }
            return rows.map(row => row[3]);
        }

        function fitCircularBoundary(points, normal, vertexTolerance) {
            if (!Array.isArray(points) || points.length < 5) return null;
            const origin = points.reduce(
                (sum, point) => sum.add(point),
                new THREE.Vector3()
            ).divideScalar(points.length);
            let uAxis = null;
            let farthest = 0;
            points.forEach(point => {
                const projected = point.clone().sub(origin);
                projected.addScaledVector(normal, -projected.dot(normal));
                if (projected.lengthSq() > farthest) {
                    farthest = projected.lengthSq();
                    uAxis = projected;
                }
            });
            if (!uAxis || uAxis.lengthSq() < vertexTolerance * vertexTolerance) return null;
            uAxis.normalize();
            const vAxis = new THREE.Vector3().crossVectors(normal, uAxis).normalize();
            const samples = points.map(point => {
                const delta = point.clone().sub(origin);
                return { x: delta.dot(uAxis), y: delta.dot(vAxis) };
            });
            let sx = 0, sy = 0, sxx = 0, syy = 0, sxy = 0;
            let sb = 0, sxb = 0, syb = 0;
            samples.forEach(sample => {
                const b = -(sample.x * sample.x + sample.y * sample.y);
                sx += sample.x;
                sy += sample.y;
                sxx += sample.x * sample.x;
                syy += sample.y * sample.y;
                sxy += sample.x * sample.y;
                sb += b;
                sxb += sample.x * b;
                syb += sample.y * b;
            });
            const solution = solveLinear3(
                [
                    [sxx, sxy, sx],
                    [sxy, syy, sy],
                    [sx, sy, samples.length],
                ],
                [sxb, syb, sb]
            );
            if (!solution) return null;
            const centerX = -solution[0] / 2;
            const centerY = -solution[1] / 2;
            const radiusSquared = centerX * centerX + centerY * centerY - solution[2];
            if (!Number.isFinite(radiusSquared) || radiusSquared <= vertexTolerance * vertexTolerance) {
                return null;
            }
            const radius = Math.sqrt(radiusSquared);
            const radialErrors = samples.map(sample => (
                Math.abs(Math.hypot(sample.x - centerX, sample.y - centerY) - radius)
            ));
            const rmsError = Math.sqrt(
                radialErrors.reduce((sum, error) => sum + error * error, 0) / radialErrors.length
            );
            const angles = samples.map(sample => (
                Math.atan2(sample.y - centerY, sample.x - centerX)
            )).sort((a, b) => a - b);
            let largestGap = 0;
            for (let index = 0; index < angles.length; index += 1) {
                const next = index === angles.length - 1
                    ? angles[0] + Math.PI * 2
                    : angles[index + 1];
                largestGap = Math.max(largestGap, next - angles[index]);
            }
            const angularCoverage = Math.PI * 2 - largestGap;
            if (rmsError > Math.max(vertexTolerance * 4, radius * 0.03)) return null;
            if (angularCoverage < Math.PI * 0.45) return null;
            return {
                localCenter: origin.clone()
                    .addScaledVector(uAxis, centerX)
                    .addScaledVector(vAxis, centerY),
                radius,
                rmsError,
                angularCoverage,
                pointCount: points.length,
            };
        }

        function planarFaceSnapCandidate(hit) {
            if (!hit || !hit.object || !hit.object.geometry || !hit.face) return null;
            const geometry = hit.object.geometry;
            const position = geometry.getAttribute
                ? geometry.getAttribute('position')
                : geometry.attributes.position;
            if (!position) return null;
            const faceIndex = Number(hit.faceIndex);
            if (!Number.isInteger(faceIndex) || faceIndex < 0) return null;

            let cache = groundPlanarSnapCache.get(geometry);
            if (!cache) {
                cache = new Map();
                groundPlanarSnapCache.set(geometry, cache);
            }
            if (cache.has(faceIndex)) return cache.get(faceIndex);

            if (!geometry.boundingBox) geometry.computeBoundingBox();
            const geometrySize = new THREE.Vector3();
            geometry.boundingBox.getSize(geometrySize);
            const diagonal = Math.max(geometrySize.length(), 1);
            const planeTolerance = Math.max(diagonal * 1e-4, 1e-5);
            const vertexTolerance = Math.max(diagonal * 1e-6, 1e-6);
            const referenceNormal = hit.face.normal.clone().normalize();
            const localHitPoint = hit.object.worldToLocal(hit.point.clone());
            const planeConstant = referenceNormal.dot(localHitPoint);
            const index = geometry.index;
            const slotCount = index ? index.count : position.count;
            const triangleCount = Math.floor(slotCount / 3);

            const vertexAt = (triangleIndex, corner) => {
                const slot = triangleIndex * 3 + corner;
                const vertexIndex = index ? index.getX(slot) : slot;
                return new THREE.Vector3().fromBufferAttribute(position, vertexIndex);
            };
            const vertexKey = vertex => [
                Math.round(vertex.x / vertexTolerance),
                Math.round(vertex.y / vertexTolerance),
                Math.round(vertex.z / vertexTolerance),
            ].join(',');
            const edgeKey = (first, second) => {
                const a = vertexKey(first);
                const b = vertexKey(second);
                return a < b ? `${a}|${b}` : `${b}|${a}`;
            };

            const candidates = new Map();
            const edgeOwners = new Map();
            const edgeGeometry = new Map();
            for (let triangleIndex = 0; triangleIndex < triangleCount; triangleIndex += 1) {
                const a = vertexAt(triangleIndex, 0);
                const b = vertexAt(triangleIndex, 1);
                const c = vertexAt(triangleIndex, 2);
                const cross = b.clone().sub(a).cross(c.clone().sub(a));
                const twiceArea = cross.length();
                if (twiceArea < 1e-12) continue;
                const normal = cross.clone().divideScalar(twiceArea);
                if (Math.abs(normal.dot(referenceNormal)) < 0.995) continue;
                if (normal.dot(referenceNormal) < 0) normal.negate();
                const planeError = Math.max(
                    Math.abs(referenceNormal.dot(a) - planeConstant),
                    Math.abs(referenceNormal.dot(b) - planeConstant),
                    Math.abs(referenceNormal.dot(c) - planeConstant)
                );
                if (planeError > planeTolerance) continue;
                const rawEdges = [[a, b], [b, c], [c, a]];
                const edges = rawEdges.map(([first, second]) => {
                    const key = edgeKey(first, second);
                    if (!edgeGeometry.has(key)) {
                        edgeGeometry.set(key, {
                            first: first.clone(),
                            second: second.clone(),
                        });
                    }
                    return key;
                });
                const triangle = {
                    index: triangleIndex,
                    a,
                    b,
                    c,
                    edges,
                    area: twiceArea / 2,
                    normal,
                    center: a.clone().add(b).add(c).divideScalar(3),
                };
                candidates.set(triangleIndex, triangle);
                edges.forEach(key => {
                    if (!edgeOwners.has(key)) edgeOwners.set(key, []);
                    edgeOwners.get(key).push(triangleIndex);
                });
            }

            let startIndex = candidates.has(faceIndex) ? faceIndex : null;
            if (startIndex === null && candidates.size > 0) {
                let bestDistance = Infinity;
                candidates.forEach(triangle => {
                    const distance = triangle.center.distanceToSquared(localHitPoint);
                    if (distance < bestDistance) {
                        bestDistance = distance;
                        startIndex = triangle.index;
                    }
                });
            }
            if (startIndex === null) return null;

            const connected = new Set();
            const queue = [startIndex];
            while (queue.length > 0) {
                const currentIndex = queue.pop();
                if (connected.has(currentIndex)) continue;
                connected.add(currentIndex);
                const triangle = candidates.get(currentIndex);
                if (!triangle) continue;
                triangle.edges.forEach(key => {
                    (edgeOwners.get(key) || []).forEach(neighbor => {
                        if (!connected.has(neighbor)) queue.push(neighbor);
                    });
                });
            }

            let totalArea = 0;
            const localCenter = new THREE.Vector3();
            const areaWeightedNormal = new THREE.Vector3();
            let minimumNormalAgreement = 1;
            const patchBox = new THREE.Box3();
            connected.forEach(triangleIndex => {
                const triangle = candidates.get(triangleIndex);
                if (!triangle) return;
                totalArea += triangle.area;
                localCenter.addScaledVector(triangle.center, triangle.area);
                areaWeightedNormal.addScaledVector(triangle.normal, triangle.area);
                minimumNormalAgreement = Math.min(
                    minimumNormalAgreement,
                    triangle.normal.dot(referenceNormal)
                );
                patchBox.expandByPoint(triangle.a);
                patchBox.expandByPoint(triangle.b);
                patchBox.expandByPoint(triangle.c);
            });
            if (totalArea <= 1e-12) return null;
            localCenter.divideScalar(totalArea);
            if (areaWeightedNormal.lengthSq() < 1e-18) return null;
            const fittedNormal = areaWeightedNormal.normalize();

            const boundaryEdges = [];
            edgeOwners.forEach((owners, key) => {
                const connectedOwners = owners.filter(owner => connected.has(owner));
                if (connectedOwners.length !== 1 || !edgeGeometry.has(key)) return;
                const edge = edgeGeometry.get(key);
                const direction = edge.second.clone().sub(edge.first);
                const length = direction.length();
                if (length <= vertexTolerance) return;
                boundaryEdges.push({
                    direction: direction.divideScalar(length),
                    length,
                    first: edge.first.clone(),
                    second: edge.second.clone(),
                    firstKey: vertexKey(edge.first),
                    secondKey: vertexKey(edge.second),
                });
            });
            boundaryEdges.sort((a, b) => b.length - a.length);
            const longestBoundary = boundaryEdges[0] || null;
            const patchSize = new THREE.Vector3();
            patchBox.getSize(patchSize);
            const patchDiagonal = Math.max(patchSize.length(), vertexTolerance);
            const longEdges = longestBoundary
                ? boundaryEdges.filter(edge => edge.length >= longestBoundary.length * 0.65)
                : [];
            const directionClusters = [];
            const clusterCosine = Math.cos(7 * Math.PI / 180);
            longEdges.forEach(edge => {
                const matches = directionClusters.some(
                    direction => Math.abs(direction.dot(edge.direction)) >= clusterCosine
                );
                if (!matches) directionClusters.push(edge.direction.clone());
            });
            const hasReliableStraightAxis = !!longestBoundary
                && longestBoundary.length >= patchDiagonal * 0.06
                && directionClusters.length > 0
                && directionClusters.length <= 3;
            let fittedTangent = hasReliableStraightAxis
                ? longestBoundary.direction.clone()
                : null;
            if (fittedTangent) {
                fittedTangent.addScaledVector(
                    fittedNormal,
                    -fittedTangent.dot(fittedNormal)
                );
                if (fittedTangent.lengthSq() < 1e-8) fittedTangent = null;
                else fittedTangent.normalize();
            }
            const boundaryGraph = new Map();
            const addBoundaryNeighbor = (key, point, neighborKey) => {
                if (!boundaryGraph.has(key)) {
                    boundaryGraph.set(key, { point: point.clone(), neighbors: new Set() });
                }
                boundaryGraph.get(key).neighbors.add(neighborKey);
            };
            boundaryEdges.forEach(edge => {
                addBoundaryNeighbor(edge.firstKey, edge.first, edge.secondKey);
                addBoundaryNeighbor(edge.secondKey, edge.second, edge.firstKey);
            });
            const visitedBoundaryVertices = new Set();
            const circleCandidates = [];
            boundaryGraph.forEach((vertex, startKey) => {
                if (visitedBoundaryVertices.has(startKey)) return;
                const queue = [startKey];
                const points = [];
                while (queue.length > 0) {
                    const key = queue.pop();
                    if (visitedBoundaryVertices.has(key)) continue;
                    visitedBoundaryVertices.add(key);
                    const item = boundaryGraph.get(key);
                    if (!item) continue;
                    points.push(item.point.clone());
                    item.neighbors.forEach(neighbor => {
                        if (!visitedBoundaryVertices.has(neighbor)) queue.push(neighbor);
                    });
                }
                const circle = fitCircularBoundary(points, fittedNormal, vertexTolerance);
                if (circle) circleCandidates.push(circle);
            });
            const result = {
                localCenter,
                localNormal: fittedNormal,
                localTangent: fittedTangent,
                circleCandidates,
                patchDiagonal,
                minimumNormalAgreement,
                boundaryDirectionClusters: directionClusters.length,
                triangleCount: connected.size,
                area: totalArea,
            };
            connected.forEach(triangleIndex => cache.set(triangleIndex, result));
            return result;
        }

        function viewerComponentForObject(object) {
            if (!object) return null;
            const cached = meshComponentByObject.get(object);
            if (cached) return cached;
            const component = Object.keys(meshDict)
                .find(name => meshDict[name] === object) || null;
            if (component) meshComponentByObject.set(object, component);
            return component;
        }

        function cadSnapCandidate(hit, planarSnap = null) {
            if (!hit || !hit.object || !treeData) return null;
            const component = viewerComponentForObject(hit.object);
            const record = component && (treeData._cad_snap_features || {})[component];
            const features = record && Array.isArray(record.features) ? record.features : [];
            if (!features.length) return null;

            const localHitPoint = hit.object.worldToLocal(hit.point.clone());
            const geometry = hit.object.geometry;
            if (geometry && !geometry.boundingBox) geometry.computeBoundingBox();
            const size = new THREE.Vector3();
            if (geometry && geometry.boundingBox) geometry.boundingBox.getSize(size);
            const diagonal = Math.max(size.length(), 1);
            const fallbackNormal = planarSnap && planarSnap.localNormal
                ? planarSnap.localNormal.clone().normalize()
                : (
                    hit.face && hit.face.normal
                        ? hit.face.normal.clone().normalize()
                        : new THREE.Vector3(0, 0, 1)
                );
            const fallbackTangent = planarSnap && planarSnap.localTangent
                ? planarSnap.localTangent.clone().normalize()
                : null;
            const priority = {
                circle_center: 0,
                arc_center: 0,
                cylinder_axis: 1,
                planar_face_center: 2,
                edge_midpoint: 3,
                vertex: 4,
            };
            let best = null;

            features.forEach(feature => {
                if (!feature || !Array.isArray(feature.position) || feature.position.length !== 3) return;
                const type = String(feature.type || '');
                if (!(type in priority)) return;
                const center = new THREE.Vector3().fromArray(feature.position);
                const normal = Array.isArray(feature.normal)
                    ? new THREE.Vector3().fromArray(feature.normal).normalize()
                    : fallbackNormal.clone();
                const tangent = Array.isArray(feature.tangent)
                    ? new THREE.Vector3().fromArray(feature.tangent).normalize()
                    : fallbackTangent && fallbackTangent.clone();
                const delta = localHitPoint.clone().sub(center);
                const radius = Number(feature.radius || 0);
                const featureCenterDistance = geometry?.boundingBox
                    ? geometry.boundingBox.distanceToPoint(center)
                    : 0;
                const maximumCadExtent = diagonal * 8;
                if (
                    featureCenterDistance > maximumCadExtent
                    || (
                        ['circle_center', 'arc_center', 'cylinder_axis'].includes(type)
                        && radius > maximumCadExtent
                    )
                ) return;
                let score = Infinity;
                let captureDistance = Math.max(diagonal * 0.012, 0.5);

                if (type === 'circle_center' || type === 'arc_center') {
                    if (!(radius > 0) || normal.lengthSq() < 0.9) return;
                    const axialDistance = Math.abs(delta.dot(normal));
                    const radial = delta.clone().addScaledVector(normal, -delta.dot(normal)).length();
                    captureDistance = Math.max(radius * 0.20, diagonal * 0.008, 0.5);
                    const rimScore = Math.hypot(Math.abs(radial - radius), axialDistance)
                        / captureDistance;
                    const centerScore = delta.length() / Math.max(captureDistance * 0.8, 0.5);
                    score = Math.min(rimScore, centerScore);
                } else if (type === 'cylinder_axis') {
                    if (!(radius > 0) || normal.lengthSq() < 0.9) return;
                    const radial = delta.clone().addScaledVector(normal, -delta.dot(normal)).length();
                    captureDistance = Math.max(radius * 0.20, diagonal * 0.008, 0.5);
                    score = Math.abs(radial - radius) / captureDistance;
                } else if (type === 'planar_face_center') {
                    const planeDistance = Math.abs(delta.dot(normal));
                    const inPlane = delta.clone().addScaledVector(normal, -delta.dot(normal)).length();
                    const areaRadius = Math.sqrt(Math.max(Number(feature.area || 0), 0) / Math.PI);
                    captureDistance = Math.max(diagonal * 0.008, 0.5);
                    const inPlaneLimit = Math.max(areaRadius * 1.35, diagonal * 0.08, 1);
                    if (planeDistance <= captureDistance && inPlane <= inPlaneLimit) {
                        score = planeDistance / captureDistance + inPlane / inPlaneLimit;
                    }
                } else {
                    captureDistance = Math.max(diagonal * 0.018, 0.75);
                    score = delta.length() / captureDistance;
                }
                if (!Number.isFinite(score) || score > 1.25) return;
                const rankedScore = priority[type] * 10 + score;
                if (!best || rankedScore < best.rankedScore) {
                    best = {
                        rankedScore,
                        feature,
                        localCenter: center,
                        localNormal: normal,
                        localTangent: tangent,
                        circleRadius: radius || null,
                    };
                }
            });

            if (!best) return null;
            return {
                localCenter: best.localCenter,
                localNormal: best.localNormal,
                localTangent: best.localTangent,
                snapMode: `cad_${best.feature.type}`,
                snapSource: 'opencascade',
                cadFeatureType: best.feature.type,
                cadEntityId: best.feature.entity_id || null,
                circleRadius: best.circleRadius,
                snapMatchScore: best.rankedScore,
                minimumNormalAgreement: 1,
                triangleCount: 0,
                patchDiagonal: diagonal,
                boundaryDirectionClusters: 0,
                area: Number(best.feature.area || 0),
            };
        }

        function snapDisplayLabel(snap) {
            const mode = String(snap && snap.snapMode || '');
            if (mode === 'cad_circle_center') return 'CAD 원 중심';
            if (mode === 'cad_arc_center') return 'CAD 호 중심';
            if (mode === 'cad_cylinder_axis') return 'CAD 원통 중심축';
            if (mode === 'cad_planar_face_center') return 'CAD 면 중심';
            if (mode === 'cad_edge_midpoint') return 'CAD 모서리 중점';
            if (mode === 'cad_vertex') return 'CAD 꼭짓점';
            if (mode === 'circular_arc_center') return '원/호 중심';
            return '면 중심';
        }

        function resolveSurfaceSnap(hit, planarSnap, preferPlanarRegion = false) {
            if (!hit) return null;
            // Ground placement is a face operation: use the centroid of the
            // connected planar region even when a circle, edge, or vertex CAD
            // snap is nearby. Joint placement keeps the exact CAD-entity
            // priority because its intent is different.
            const exactCadSnap = preferPlanarRegion
                ? null
                : cadSnapCandidate(hit, planarSnap);
            if (exactCadSnap) return exactCadSnap;
            if (!planarSnap) return null;
            const localHitPoint = hit.object.worldToLocal(hit.point.clone());
            let bestCircle = null;
            let bestScore = Infinity;
            (planarSnap.circleCandidates || []).forEach(circle => {
                const radialDistance = localHitPoint.distanceTo(circle.localCenter);
                const edgeDistance = Math.abs(radialDistance - circle.radius);
                const captureDistance = Math.max(
                    circle.radius * 0.22,
                    Number(planarSnap.patchDiagonal || 0) * 0.012
                );
                const score = edgeDistance / Math.max(captureDistance, 1e-9);
                if (score <= 1 && score < bestScore) {
                    bestScore = score;
                    bestCircle = circle;
                }
            });
            if (bestCircle) {
                return {
                    ...planarSnap,
                    localCenter: bestCircle.localCenter.clone(),
                    snapMode: 'circular_arc_center',
                    circleRadius: bestCircle.radius,
                    circleFitError: bestCircle.rmsError,
                };
            }
            return {
                ...planarSnap,
                localCenter: planarSnap.localCenter.clone(),
                snapMode: 'connected_planar_face_centroid',
            };
        }

        function updateGroundFaceSnapPreview(event) {
            if ((!groundFacePickMode && !baseFootprintPickMode && !jointOriginPickMode) || !event) return;
            const intersections = getViewerIntersections(
                event,
                { refreshMatrices: false }
            );
            const selection = resolveBestSurfaceSnap(
                intersections,
                event,
                { hoverOnly: true }
            );
            if (!selection) {
                if (jointOriginPickMode) hideJointSnapMarker();
                else hideGroundSnapMarker();
                return;
            }
            const { hit, snap } = selection;
            const component = selection.component || '선택한 부품';
            const worldCenter = hit.object.localToWorld(snap.localCenter.clone());
            const worldNormal = snap.localNormal
                ? snap.localNormal.clone().transformDirection(hit.object.matrixWorld).normalize()
                : new THREE.Vector3(0, 1, 0);
            if (jointOriginPickMode) {
                showJointSnapMarker(worldCenter, worldNormal, snap.circleRadius, false);
            } else {
                showGroundSnapMarker(worldCenter, worldNormal, false, snap.circleRadius);
            }
            const directionHint = snap.snapSource === 'opencascade'
                ? ` · ${snapDisplayLabel(snap)} 정확 스냅${
                    selection.candidateCount > 1
                        ? ` · 겹친 후보 ${selection.candidateCount}개 (Shift: 다음 후보)`
                        : ''
                }`
                : snap.snapMode === 'circular_arc_center'
                ? ` · 원/호 중심 자석 (${Number(snap.circleRadius).toFixed(2)})`
                : (
                    snap.localTangent
                        ? ' · 긴 모서리 방향 감지'
                        : ' · 원형/대칭면은 부모 링크 X방향 사용'
                );
            if (jointOriginPickMode) {
                updateJointSnapCandidateControls(selection);
                updateJointOriginPickUi(
                    `자석 중심: ${component}${directionHint} · 클릭하면 이 점이 조인트 원점, 면의 법선이 축이 됩니다.`
                );
            } else if (baseFootprintPickMode) {
                updateBaseFootprintPickUi(
                    `BASE FOOTPRINT 후보: ${component}${directionHint} · 클릭하면 이 위치만 별도로 저장됩니다.`
                );
            } else {
                updateGroundFaceUi(
                    `자석 중심: ${component}${directionHint} · 클릭하면 월드 XYZ 0,0,0이 됩니다.`
                );
            }
        }

        function scheduleGroundFaceSnapPreview(event) {
            groundSnapHoverEvent = {
                clientX: event.clientX,
                clientY: event.clientY,
            };
            if (groundSnapHoverFrame) return;
            groundSnapHoverFrame = requestAnimationFrame(() => {
                groundSnapHoverFrame = null;
                const now = performance.now();
                if (now - groundSnapLastHoverAt < 75) return;
                groundSnapLastHoverAt = now;
                updateGroundFaceSnapPreview(groundSnapHoverEvent);
            });
        }

        function updateBaseFootprintPickUi(message) {
            const status = document.getElementById('viewer-pick-status');
            if (!status) return;
            status.textContent = message;
            status.style.display = 'block';
            clearTimeout(status._hideTimer);
            if (!baseFootprintPickMode) {
                status._hideTimer = setTimeout(() => { status.style.display = 'none'; }, 3200);
            }
        }

        function currentGroundOriginOffset() {
            const stored = treeData?._preview_ground_face?.origin_offset_xyz;
            if (!Array.isArray(stored) || stored.length !== 3) return [0, 0, 0];
            return stored.map(value => Number.isFinite(Number(value)) ? Number(value) : 0);
        }

        function updateGroundOriginOffsetInputs() {
            const offset = currentGroundOriginOffset();
            ['x', 'y', 'z'].forEach((axis, index) => {
                const input = document.getElementById(`ground-offset-${axis}`);
                if (!input || document.activeElement === input) return;
                input.value = String(Number((offset[index] * 1000).toFixed(3)));
            });
        }

        function rosOffsetMetersToViewer(offset) {
            const unitsPerMeter = Number(treeData?._preview_units_per_meter) || 1000.0;
            // ROS uses Z-up while the Three.js preview uses Y-up.
            return new THREE.Vector3(offset[0], offset[2], -offset[1])
                .multiplyScalar(unitsPerMeter);
        }

        function setGroundOriginOffset(axis, rawValue) {
            if (!treeData?._preview_ground_face || !robotRoot) return;
            const axisIndex = { x: 0, y: 1, z: 2 }[String(axis).toLowerCase()];
            const millimeters = Number(rawValue);
            if (axisIndex === undefined || !Number.isFinite(millimeters)) {
                updateGroundOriginOffsetInputs();
                updateGroundFaceUi('위치 보정값은 유한한 숫자로 입력하세요.');
                return;
            }
            const value = millimeters / 1000;
            const previous = currentGroundOriginOffset();
            if (Math.abs(previous[axisIndex] - value) <= 1e-12) return;
            saveState();
            const next = previous.slice();
            next[axisIndex] = value;
            const delta = next.map((item, index) => item - previous[index]);
            robotRoot.position.add(rosOffsetMetersToViewer(delta));
            robotRoot.updateMatrixWorld(true);
            treeData._preview_ground_face.origin_offset_xyz = next;
            syncPreviewRootTransform();
            updateGroundOriginOffsetInputs();
            refreshWorldReferencePlane(0);
            render({ skipPreview: true });
            updateGroundFaceUi(
                `모델 위치 보정 적용: X ${(next[0] * 1000).toFixed(1)}, Y ${(next[1] * 1000).toFixed(1)}, Z ${(next[2] * 1000).toFixed(1)} mm`
            );
        }

        function updateGroundFaceUi(message) {
            const button = document.getElementById('ground-face-button');
            const help = document.getElementById('ground-face-help');
            const container = document.getElementById('viewer-3d-container');
            const panel = document.getElementById('ground-origin-panel');
            const state = document.getElementById('ground-origin-state');
            const hasGroundOrigin = !!treeData?._preview_ground_face;
            if (button) {
                button.classList.toggle('active', groundFacePickMode);
                button.textContent = groundFacePickMode
                    ? '✕ 지정 취소'
                    : hasGroundOrigin
                        ? '변경'
                        : '바닥면·원점 지정';
            }
            if (panel) {
                panel.classList.toggle('is-picking', groundFacePickMode);
                panel.classList.toggle('is-complete', hasGroundOrigin);
            }
            if (state) {
                state.textContent = hasGroundOrigin ? '설정 완료' : '필수 설정';
            }
            if (container) {
                container.classList.toggle('ground-face-picking', groundFacePickMode || baseFootprintPickMode);
                container.classList.toggle('joint-origin-picking', jointOriginPickMode);
            }
            updateGroundOriginOffsetInputs();
            if (help && message) help.textContent = message;
        }

        function toggleGroundFacePick() {
            if (jointOriginPickMode) cancelJointOriginPick();
            baseFootprintPickMode = false;
            activeJointSnapMarkerInfo = null;
            hideJointSnapMarker();
            groundFacePickMode = !groundFacePickMode;
            if (!groundFacePickMode) hideGroundSnapMarker();
            updateGroundFaceUi(
                groundFacePickMode
                    ? '평평한 면 위로 마우스를 옮겨 노란 중심점이 나타나면 클릭하세요.'
                    : '바닥면 지정을 취소했습니다.'
            );
        }

        function resetGroundFace() {
            if (!treeData || !robotRoot) return;
            saveState();
            groundFacePickMode = false;
            baseFootprintPickMode = false;
            hideGroundSnapMarker();
            clearCustomGroundTransform();
            applyRobotRootUpAxis(resolvePreviewUpAxis());
            fitCameraToRobot();
            updateGroundFaceUi('CAD 종류에 맞는 자동 위쪽 축으로 복원했습니다.');
        }

        function fitCameraToRobot() {
            if (!camera || !controls || !gridHelper) return;
            const box = new THREE.Box3();
            Object.values(meshDict).forEach(mesh => box.expandByObject(mesh));
            if (box.isEmpty()) return;
            const center = new THREE.Vector3();
            const size = new THREE.Vector3();
            box.getCenter(center);
            box.getSize(size);
            const maxDim = Math.max(size.x, size.y, size.z);
            const fov = camera.fov * Math.PI / 180;
            let distance = Math.abs(maxDim / 2 / Math.tan(fov / 2)) * 2.0;
            if (!Number.isFinite(distance) || distance < 100) distance = 500;
            camera.position.set(
                center.x + distance * 0.6,
                center.y + distance * 0.5,
                center.z + distance
            );
            controls.target.copy(center);
            refreshWorldReferencePlane(
                treeData?._preview_ground_face ? 0 : box.min.y,
                maxDim
            );
            camera.updateProjectionMatrix();
            controls.update();
        }

        function worldFrameVisibilityEnabled() {
            const checkbox = Array.from(
                document.querySelectorAll('.preview-control-row input[type="checkbox"]')
            ).find(input => input.getAttribute('onchange')?.includes('toggleWorldFrame'));
            return checkbox ? !!checkbox.checked : true;
        }

        function refreshWorldReferencePlane(groundY = 0, modelSpan = null) {
            if (!scene) return;
            let span = Number(modelSpan);
            if (!Number.isFinite(span) || span <= 0) {
                const box = new THREE.Box3();
                Object.values(meshDict).forEach(mesh => box.expandByObject(mesh));
                if (!box.isEmpty()) {
                    const size = new THREE.Vector3();
                    box.getSize(size);
                    span = Math.max(size.x, size.y, size.z);
                }
            }
            if (!Number.isFinite(span) || span <= 0) span = 1000;

            const gridSize = Math.max(10, Math.min(100000, span * 5));
            const gridDivisions = 40;
            const visible = worldFrameVisibilityEnabled();
            if (gridHelper) {
                scene.remove(gridHelper);
                gridHelper.geometry?.dispose();
                if (Array.isArray(gridHelper.material)) {
                    gridHelper.material.forEach(material => material.dispose());
                } else {
                    gridHelper.material?.dispose();
                }
            }
            gridHelper = new THREE.GridHelper(
                gridSize,
                gridDivisions,
                0x607784,
                0x3b454b
            );
            const groundOffset = Math.max(gridSize * 0.00001, 0.0001);
            gridHelper.position.y = Number(groundY) - groundOffset;
            gridHelper.visible = visible;
            gridHelper.renderOrder = -2;
            const materials = Array.isArray(gridHelper.material)
                ? gridHelper.material
                : [gridHelper.material];
            materials.forEach(material => {
                material.transparent = true;
                material.opacity = 0.62;
                material.depthWrite = false;
            });
            scene.add(gridHelper);

            if (worldFrameHelper) {
                const frameScale = Math.max(span * 0.28, gridSize / gridDivisions);
                worldFrameHelper.scale.setScalar(frameScale / 500);
                worldFrameHelper.position.set(0, 0, 0);
                worldFrameHelper.visible = visible;
            }
        }

        function setPreviewUpAxis(axis) {
            const normalized = ['x', 'y', 'z'].includes(axis) ? axis : 'z';
            if (treeData) {
                saveState();
                treeData._preview_up_axis = normalized;
                clearCustomGroundTransform();
            }
            groundFacePickMode = false;
            baseFootprintPickMode = false;
            hideGroundSnapMarker();
            applyRobotRootUpAxis(normalized);
            fitCameraToRobot();
            updateGroundFaceUi('위쪽 축을 적용했습니다. 필요하면 바닥면을 직접 지정할 수 있습니다.');
        }

        // --- 3D 뷰어 초기화 로직 ---
        function init3D() {
            const container = document.getElementById('viewer-3d-container');
            const viewerStatus = document.getElementById('viewer-status');
            const initialWidth = Math.max(container.clientWidth, container.parentElement ? container.parentElement.clientWidth : 0, 320);
            const initialHeight = Math.max(container.clientHeight, container.parentElement ? container.parentElement.clientHeight : 0, 240);
            
            scene = new THREE.Scene();
            scene.background = new THREE.Color(0x222222);
            scene.add(new THREE.HemisphereLight(0xffffff, 0x303030, 1.15));
            const keyLight = new THREE.DirectionalLight(0xffffff, 0.85);
            keyLight.position.set(1, 2, 3);
            scene.add(keyLight);

            robotRoot = new THREE.Group();
            const initialUpAxis = resolvePreviewUpAxis();
            const restoredRootTransform = applyStoredRobotRootTransform();
            if (!restoredRootTransform) {
                applyRobotRootUpAxis(initialUpAxis);
            } else {
                // Migrate legacy Three.js XYZ Euler values to URDF-compatible
                // roll-pitch-yaw while preserving the authoritative quaternion.
                syncPreviewRootTransform();
            }
            scene.add(robotRoot);
            const upAxisSelect = document.getElementById('preview-up-axis');
            if (upAxisSelect) upAxisSelect.value = initialUpAxis;
            if (treeData && treeData._preview_ground_face) {
                updateGroundFaceUi(`저장된 바닥면: ${treeData._preview_ground_face.component || '사용자 지정 면'}`);
            }
            
            // 로봇 크기를 고려해 매우 큰 그리드
            gridHelper = new THREE.GridHelper(5000, 50, 0x607784, 0x3b454b);
            scene.add(gridHelper);
            
            // X, Y, Z 축 표시 (크기 500)
            worldFrameHelper = new THREE.AxesHelper(500);
            // Three.js is Y-up, while every coordinate shown/exported by this
            // editor is ROS Z-up. Rotate the visual world axes into the same
            // convention as BASE FOOTPRINT: X red, Y green, Z blue.
            worldFrameHelper.rotation.x = -Math.PI / 2;
            scene.add(worldFrameHelper);

            // 💡 렌더링 확인용 테스트 큐브 (와이어프레임) 추가

            // 카메라 시야(Clipping Plane)를 매우 넓게 설정
            camera = new THREE.PerspectiveCamera(45, initialWidth / initialHeight, 0.1, 1000000);
            camera.position.set(500, 500, 500); 
            
            renderer = new THREE.WebGLRenderer({
                antialias: !PETASOS_LOW_SPEC_RENDERING,
                powerPreference: 'high-performance'
            });
            renderer.setSize(initialWidth, initialHeight);
            container.appendChild(renderer.domElement);
            
            controls = new THREE.OrbitControls(camera, renderer.domElement);
            controls.enableDamping = true;
            controls.dampingFactor = 0.05;
            controls.mouseButtons.MIDDLE = THREE.MOUSE.PAN;
            controls.addEventListener('start', beginViewerCameraGesture);
            controls.addEventListener('end', endViewerCameraGesture);
            renderer.domElement.addEventListener('pointerdown', event => {
                hideViewerContextMenu();
                if (event.button === 0) {
                    viewerPointerDown = { x: event.clientX, y: event.clientY, time: performance.now() };
                    viewerPointerDragged = false;
                } else if (event.button === 2) {
                    viewerRightPointerDown = { x: event.clientX, y: event.clientY };
                    viewerRightPointerDragged = false;
                }
            });
            renderer.domElement.addEventListener('pointermove', event => {
                if ((groundFacePickMode || baseFootprintPickMode || jointOriginPickMode) && !viewerPointerDown) {
                    scheduleGroundFaceSnapPreview(event);
                }
                if (viewerPointerDown && Math.hypot(
                    event.clientX - viewerPointerDown.x,
                    event.clientY - viewerPointerDown.y
                ) > 5) {
                    viewerPointerDragged = true;
                }
                if (viewerRightPointerDown && Math.hypot(
                    event.clientX - viewerRightPointerDown.x,
                    event.clientY - viewerRightPointerDown.y
                ) > 5) {
                    viewerRightPointerDragged = true;
                }
            });
            renderer.domElement.addEventListener('pointerup', event => {
                if (event.button === 2) {
                    viewerRightPointerDown = null;
                    return;
                }
                if (event.button !== 0) return;
                const shouldPick = !viewerPointerDragged;
                viewerPointerDown = null;
                viewerPointerDragged = false;
                if (!shouldPick) return;
                if (jointOriginPickMode || groundFacePickMode || baseFootprintPickMode) {
                    suppressViewerDoubleClickUntil = performance.now() + 450;
                    if (jointOriginPickMode) handleJointOriginPick(event);
                    else if (baseFootprintPickMode) handleBaseFootprintPick(event);
                    else handleGroundFacePick(event);
                    return;
                }
                if (viewerSingleClickTimer) clearTimeout(viewerSingleClickTimer);
                const pickEvent = {
                    clientX: event.clientX,
                    clientY: event.clientY,
                    ctrlKey: event.ctrlKey,
                    metaKey: event.metaKey,
                };
                viewerSingleClickTimer = setTimeout(() => {
                    viewerSingleClickTimer = null;
                    handleViewerMeshSelect(pickEvent);
                }, 300);
            });
            renderer.domElement.addEventListener('dblclick', event => {
                if (performance.now() < suppressViewerDoubleClickUntil) return;
                if (viewerSingleClickTimer) {
                    clearTimeout(viewerSingleClickTimer);
                    viewerSingleClickTimer = null;
                }
                const shouldPick = !viewerPointerDragged;
                viewerPointerDown = null;
                viewerPointerDragged = false;
                if (!shouldPick) return;
                if (jointOriginPickMode) {
                    handleJointOriginPick(event);
                } else if (baseFootprintPickMode) {
                    handleBaseFootprintPick(event);
                } else if (groundFacePickMode) {
                    handleGroundFacePick(event);
                } else {
                    handleViewerMeshPick(event);
                }
            });
            renderer.domElement.addEventListener('contextmenu', event => {
                event.preventDefault();
                const wasDragged = viewerRightPointerDragged;
                viewerRightPointerDown = null;
                viewerRightPointerDragged = false;
                if (wasDragged) {
                    hideViewerContextMenu();
                    return;
                }
                showViewerContextMenu(event);
            });
            
            const loader = new THREE.STLLoader();
            const previewTransforms = treeData._preview_transforms || {};
            const meshRevision = encodeURIComponent(treeData._mesh_revision || 'current');
            
            const flatLinks = getFlatLinks(treeData, null, -1);
            const allComponents = new Set();
            flatLinks.forEach(item => {
                item.node.components.forEach(comp => allComponents.add(comp));
            });
            
            if (allComponents.size === 0) {
                console.warn("No components found to load in 3D viewer.");
                if (viewerStatus) viewerStatus.innerText = '조립품을 불러오면 3D 형상이 표시됩니다.';
                animate();
                return;
            }

            let loadedCount = 0;
            let failedCount = 0;
            const boundingBox = new THREE.Box3();

            function finalizeMeshLoading() {
                loadedCount++;
                if (viewerStatus) {
                    viewerStatus.innerText = `3D mesh loading... ${loadedCount}/${allComponents.size}`;
                }
                if (loadedCount !== allComponents.size) return;

                // Apply materials once after all asynchronous mesh loads. Doing
                // this for every part makes large assemblies O(n²).
                refreshViewerColors();

                if (repairStoredGroundTransformIfBelowPlane()) {
                    boundingBox.makeEmpty();
                    Object.values(meshDict).forEach(mesh => boundingBox.expandByObject(mesh));
                }
                if (!boundingBox.isEmpty()) {
                    const center = new THREE.Vector3();
                    boundingBox.getCenter(center);
                    const size = new THREE.Vector3();
                    boundingBox.getSize(size);
                    const maxDim = Math.max(size.x, size.y, size.z);
                    const fov = camera.fov * (Math.PI / 180);
                    let cameraZ = Math.abs(maxDim / 2 / Math.tan(fov / 2));
                    cameraZ *= 2.0;
                    if (cameraZ < 100 || !isFinite(cameraZ)) cameraZ = 500;

                    camera.position.set(center.x + cameraZ * 0.6, center.y + cameraZ * 0.5, center.z + cameraZ);
                    controls.target.copy(center);
                    camera.updateProjectionMatrix();
                    controls.update();

                    refreshWorldReferencePlane(
                        treeData?._preview_ground_face ? 0 : boundingBox.min.y,
                        maxDim
                    );
                }

                buildPreviewJointRig();
                buildPreviewFrames();
                renderPreviewJointControls();
                showBaseFootprintFrameMarker();

                if (viewerStatus) {
                    const importWarnings = (treeData._import_report && treeData._import_report.warnings) || [];
                    if (failedCount > 0) {
                        viewerStatus.classList.add('error');
                        viewerStatus.innerText = `3D preview loaded with ${failedCount} missing mesh file(s).`;
                    } else if (importWarnings.length > 0) {
                        viewerStatus.classList.toggle('error', !!treeData._import_report.has_errors);
                        viewerStatus.innerText = `가져오기 완료 · ${importWarnings.length}개 확인 항목이 있습니다.`;
                    } else {
                        viewerStatus.remove();
                    }
                }
            }

            allComponents.forEach(comp => {
                const stlUrl = '/meshes/' + encodeURIComponent(comp) + '.stl?v=' + meshRevision;
                
                loader.load(stlUrl, function (geometry) {
                    const mesh = new THREE.Mesh(geometry, defaultMaterial);
                    scheduleMeshEdges(mesh, geometry, comp);
                    const transformValues = previewTransforms[comp];
                    if (transformValues && transformValues.length === 16) {
                        const previewMatrix = new THREE.Matrix4();
                        previewMatrix.fromArray(transformValues);
                        mesh.applyMatrix4(previewMatrix);
                    }
                    mesh.updateMatrixWorld(true);
                    robotRoot.add(mesh);
                    robotRoot.updateMatrixWorld(true);
                    meshDict[comp] = mesh;
                    meshComponentByObject.set(mesh, comp);

                    const collisionMesh = new THREE.Mesh(
                        geometry,
                        new THREE.MeshBasicMaterial({ color: 0xff9800, wireframe: true, transparent: true, opacity: 0.9 })
                    );
                    collisionMesh.visible = false;
                    if (transformValues && transformValues.length === 16) {
                        const collisionMatrix = new THREE.Matrix4();
                        collisionMatrix.fromArray(transformValues);
                        collisionMesh.applyMatrix4(collisionMatrix);
                    }
                    robotRoot.add(collisionMesh);
                    collisionMeshDict[comp] = collisionMesh;
                    
                    geometry.computeBoundingBox();
                    if(geometry.boundingBox) {
                        const box = geometry.boundingBox.clone();
                        box.applyMatrix4(mesh.matrixWorld);
                        boundingBox.union(box);
                    }

                    finalizeMeshLoading();
                    return;
                    if (loadedCount === allComponents.size) {
                        const center = new THREE.Vector3();
                        boundingBox.getCenter(center);
                        const size = new THREE.Vector3();
                        boundingBox.getSize(size);
                        
                        
                        const maxDim = Math.max(size.x, size.y, size.z);
                        const fov = camera.fov * (Math.PI / 180);
                        let cameraZ = Math.abs(maxDim / 2 / Math.tan(fov / 2));
                        cameraZ *= 2.0; // 충분한 여백 확보
                        
                        if (cameraZ < 100 || !isFinite(cameraZ)) cameraZ = 500;

                        camera.position.set(center.x + cameraZ * 0.6, center.y + cameraZ * 0.5, center.z + cameraZ);
                        controls.target.copy(center);
                        camera.updateProjectionMatrix();
                        controls.update();
                        
                        if (isFinite(boundingBox.min.y)) {
                            gridHelper.position.y = boundingBox.min.y;
                        }

                        buildPreviewJointRig();
                        buildPreviewFrames();
                        renderPreviewJointControls();
                    }
                }, undefined, function (error) {
                    console.error('An error happened loading STL (' + comp + '): ', error);
                    failedCount++;
                    finalizeMeshLoading();
                });
            });

            window.addEventListener('resize', onWindowResize, false);
            window.addEventListener('resize', scheduleTreeWireRender, false);
            if (window.ResizeObserver) {
                viewerResizeObserver = new ResizeObserver(onWindowResize);
                viewerResizeObserver.observe(container);
            } else {
                // 구형 브라우저에서만 가벼운 크기 확인을 사용합니다.
                window.setInterval(onWindowResize, 1500);
            }
            animate();
        }

        function onWindowResize() {
            const container = document.getElementById('viewer-3d-container');
            if(!container || !camera || !renderer) return;
            const width = Math.max(container.clientWidth, container.parentElement ? container.parentElement.clientWidth : 0, 320);
            const height = Math.max(container.clientHeight, container.parentElement ? container.parentElement.clientHeight : 0, 240);
            if (width === viewerResizeWidth && height === viewerResizeHeight) return;
            viewerResizeWidth = width;
            viewerResizeHeight = height;
            camera.aspect = width / height;
            camera.updateProjectionMatrix();
            renderer.setSize(width, height, false);
        }

        function animate(frameTime = 0) {
            requestAnimationFrame(animate);
            if (
                PREVIEW_FRAME_INTERVAL_MS > 0
                && frameTime - previewLastFrameAt < PREVIEW_FRAME_INTERVAL_MS
            ) return;
            previewLastFrameAt = frameTime;
            controls.update();
            renderer.render(scene, camera);
        }

        function collectNodeComponents(node, result = []) {
            (node.components || []).forEach(comp => result.push(comp));
            (node.children || []).forEach(child => collectNodeComponents(child.link_group, result));
            return result;
        }

        function buildPreviewFrames() {
            linkFrameHelpers.forEach(helper => {
                if (helper.parent) helper.parent.remove(helper);
            });
            inertiaMarkers.forEach(marker => {
                if (marker.parent) marker.parent.remove(marker);
            });
            linkFrameHelpers = [];
            inertiaMarkers = [];

            const flatLinks = getFlatLinks(treeData, null, -1);
            flatLinks.forEach(item => {
                const pivot = item.node._pivot || robotRoot;
                const frame = new THREE.AxesHelper(120);
                frame.visible = false;
                pivot.add(frame);
                linkFrameHelpers.push(frame);

                const box = new THREE.Box3();
                item.node.components.forEach(comp => {
                    const mesh = meshDict[comp];
                    if (mesh) box.expandByObject(mesh);
                });
                if (box.isEmpty()) return;

                const center = new THREE.Vector3();
                box.getCenter(center);

                const marker = new THREE.Mesh(
                    new THREE.SphereGeometry(18, 16, 16),
                    new THREE.MeshBasicMaterial({ color: 0x10b981, transparent: true, opacity: 0.72 })
                );
                pivot.updateMatrixWorld(true);
                pivot.worldToLocal(center);
                marker.position.copy(center);
                marker.visible = false;
                pivot.add(marker);
                inertiaMarkers.push(marker);
            });
        }

        function ensureJointMotionLimits(jointType, jointInfo) {
            if (!jointInfo) return;
            const lower = Number(jointInfo.lower_limit);
            const upper = Number(jointInfo.upper_limit);
            const hasUsableRange = Number.isFinite(lower)
                && Number.isFinite(upper)
                && upper - lower > 1e-9;
            if (jointType === 'revolute' && !hasUsableRange) {
                jointInfo.lower_limit = -Math.PI;
                jointInfo.upper_limit = Math.PI;
            } else if (jointType === 'prismatic' && !hasUsableRange) {
                jointInfo.lower_limit = -0.1;
                jointInfo.upper_limit = 0.1;
            }
        }

        function buildPreviewJointRig() {
            clearPreviewJointRig();
            previewJointControllers = [];
            const previewUnitsPerMeter = treeData._preview_units_per_meter || 100.0;

            function attachSubtreeToPivot(node, pivot) {
                Object.defineProperty(node, '_pivot', {
                    value: pivot,
                    writable: true,
                    configurable: true,
                    enumerable: false
                });
                collectNodeComponents(node).forEach(comp => {
                    const mesh = meshDict[comp];
                    const collisionMesh = collisionMeshDict[comp];
                    if (mesh) pivot.attach(mesh);
                    if (collisionMesh) pivot.attach(collisionMesh);
                });
            }

            Object.defineProperty(treeData, '_pivot', {
                value: robotRoot,
                writable: true,
                configurable: true,
                enumerable: false
            });

            function walk(node, parentContainer) {
                (node.children || []).forEach(child => {
                    if (!isPatcherJointActive(child)) {
                        // Recovery/fixed-candidate edges only keep otherwise
                        // disconnected CAD occurrences inside the editor tree.
                        // Their meshes already use absolute CAD transforms, so
                        // never create a movable pivot or a visible joint frame.
                        Object.defineProperty(child.link_group, '_pivot', {
                            value: robotRoot,
                            writable: true,
                            configurable: true,
                            enumerable: false
                        });
                        walk(child.link_group, robotRoot);
                        return;
                    }
                    const jointInfo = child.joint_info || {};
                    ensureJointMotionLimits(child.joint_type || jointInfo.type || 'fixed', jointInfo);
                    const xyz = jointInfo.xyz || [0, 0, 0];
                    const rpy = jointInfo._manual_rpy || jointInfo.rpy || [0, 0, 0];
                    const axisValues = jointInfo.axis || [0, 0, 1];
                    const axis = new THREE.Vector3(axisValues[0], axisValues[1], axisValues[2]);
                    if (axis.lengthSq() === 0) axis.set(0, 0, 1);
                    axis.normalize();

                    const jointOffset = new THREE.Vector3(
                        xyz[0] * previewUnitsPerMeter,
                        xyz[1] * previewUnitsPerMeter,
                        xyz[2] * previewUnitsPerMeter
                    );
                    const previewWorldXyz = jointInfo._preview_world_xyz;
                    if (previewWorldXyz && previewWorldXyz.length === 3) {
                        const previewWorldPoint = new THREE.Vector3(
                            previewWorldXyz[0] * previewUnitsPerMeter,
                            previewWorldXyz[1] * previewUnitsPerMeter,
                            previewWorldXyz[2] * previewUnitsPerMeter
                        );
                        parentContainer.updateMatrixWorld(true);
                        robotRoot.localToWorld(previewWorldPoint);
                        parentContainer.worldToLocal(previewWorldPoint);
                        jointOffset.copy(previewWorldPoint);
                    }

                    const pivot = new THREE.Group();
                    // Prefer the Fusion/world preview origin for visual rigging,
                    // converted into the current parent pivot's local frame.
                    pivot.position.copy(jointOffset);
                    pivot.rotation.order = 'ZYX';
                    const previewWorldQuaternion = jointInfo._preview_world_quaternion;
                    const previewQuaternion = jointInfo._preview_local_quaternion;
                    if (
                        Array.isArray(previewWorldQuaternion)
                        && previewWorldQuaternion.length === 4
                        && previewWorldQuaternion.every(Number.isFinite)
                    ) {
                        robotRoot.updateMatrixWorld(true);
                        parentContainer.updateMatrixWorld(true);
                        const robotWorldQuaternion = new THREE.Quaternion();
                        const parentWorldQuaternion = new THREE.Quaternion();
                        robotRoot.getWorldQuaternion(robotWorldQuaternion);
                        parentContainer.getWorldQuaternion(parentWorldQuaternion);
                        const desiredWorldQuaternion = robotWorldQuaternion.multiply(
                            new THREE.Quaternion().fromArray(previewWorldQuaternion).normalize()
                        );
                        pivot.quaternion.copy(
                            parentWorldQuaternion.invert().multiply(desiredWorldQuaternion)
                        ).normalize();
                    } else if (
                        Array.isArray(previewQuaternion)
                        && previewQuaternion.length === 4
                        && previewQuaternion.every(Number.isFinite)
                    ) {
                        pivot.quaternion.fromArray(previewQuaternion).normalize();
                    } else {
                        pivot.rotation.set(rpy[0], rpy[1], rpy[2]);
                    }
                    const childDisabled = isJointDisabled(child) || isLinkDisabled(child.link_group);
                    if (childDisabled) {
                        pivot.visible = false;
                    }
                    parentContainer.add(pivot);
                    attachSubtreeToPivot(child.link_group, pivot);

                    previewPivotGroups.push(pivot);

                    // The frame belongs to the joint pivot, so it moves with
                    // prismatic joints and rotates with revolute joints.
                    const jointFrame = new THREE.AxesHelper(120);
                    jointFrame.visible = false;
                    jointFrame.userData.petasosJoint = child;
                    jointFrame.userData.petasosJointName = child.joint_name;
                    pivot.add(jointFrame);
                    jointFrameHelpers.push(jointFrame);

                    if (!childDisabled) {
                        const storedInitialPosition = Number(jointInfo.initial_position);
                        const initialPreviewValue = Number.isFinite(storedInitialPosition)
                            ? (
                                (child.joint_type || jointInfo.type) === 'prismatic'
                                    ? storedInitialPosition
                                    : THREE.MathUtils.radToDeg(storedInitialPosition)
                            )
                            : 0;
                        previewJointControllers.push({
                            name: child.joint_name,
                            type: child.joint_type || jointInfo.type || 'fixed',
                            jointObj: child,
                            jointInfo,
                            axis,
                            pivot,
                            basePosition: pivot.position.clone(),
                            baseQuaternion: pivot.quaternion.clone(),
                            unitsPerMeter: previewUnitsPerMeter,
                            lowerLimit: jointInfo.lower_limit,
                            upperLimit: jointInfo.upper_limit,
                            value: initialPreviewValue
                        });

                        // Apply the exported initial pose before constructing the
                        // child pivots so nested joints inherit the configured pose.
                        setPreviewJointValue(
                            previewJointControllers.length - 1,
                            initialPreviewValue
                        );
                    }

                    walk(child.link_group, pivot);
                });
            }

            walk(treeData, robotRoot);
            attachJointSnapMarkerToRig();
            applyPreviewControlState();
            applyViewerIsolationVisibility();
            previewRigReady = true;
            previewRigDirty = false;
            previewControlsDirty = false;
        }

        function clearPreviewJointRig() {
            robotRoot.updateMatrixWorld(true);

            function restoreStoredComponentTransform(component, mesh) {
                if (!mesh || !robotRoot) return;
                if (mesh.parent) robotRoot.attach(mesh);
                const values = treeData?._preview_transforms?.[component];
                if (!Array.isArray(values) || values.length !== 16) return;
                const storedMatrix = new THREE.Matrix4().fromArray(values);
                storedMatrix.decompose(mesh.position, mesh.quaternion, mesh.scale);
                mesh.updateMatrix();
                mesh.updateMatrixWorld(true);
            }

            // A rig rebuild can happen while several joints are already at a
            // non-zero preview pose.  Start again from the stored component
            // transforms; otherwise preserving the posed world transforms and
            // applying initial_position again doubles every ancestor motion.
            Object.entries(meshDict).forEach(([component, mesh]) => {
                restoreStoredComponentTransform(component, mesh);
            });
            Object.entries(collisionMeshDict).forEach(([component, mesh]) => {
                restoreStoredComponentTransform(component, mesh);
            });

            jointFrameHelpers.forEach(helper => {
                if (helper.parent) helper.parent.remove(helper);
            });
            jointFrameHelpers = [];

            previewPivotGroups.slice().reverse().forEach(group => {
                if (group.parent) group.parent.remove(group);
            });
            previewPivotGroups = [];
        }

        function applyPreviewControlState() {
            const jointFramesToggle = document.getElementById('show-joint-frames');
            const jointFrameSize = document.getElementById('joint-frame-size');
            toggleJointFrames(jointFramesToggle ? jointFramesToggle.checked : false);
            resizeJointFrames(jointFrameSize ? jointFrameSize.value : 120);
        }

        function refreshPreviewRig() {
            if (!previewRigReady || !robotRoot) return;
            buildPreviewJointRig();
            buildPreviewFrames();
            renderPreviewJointControls();
            if (pendingPreviewPoseRestore) {
                restorePreviewJointPose(pendingPreviewPoseRestore);
                pendingPreviewPoseRestore = null;
            }
        }

        function updatePreviewIfNeeded() {
            if (!previewRigReady || !robotRoot) return;
            if (previewRigDirty) {
                refreshPreviewRig();
                if (selectedElement && selectedElement.type === 'joint') {
                    updatePanel();
                }
            } else if (previewControlsDirty) {
                renderPreviewJointControls();
                previewControlsDirty = false;
            }
        }

        function schedulePreviewUpdate(delay = 120) {
            if (!previewRigReady || !robotRoot) return;
            if (previewUpdateTimer) clearTimeout(previewUpdateTimer);
            previewUpdateTimer = setTimeout(() => {
                previewUpdateTimer = null;
                updatePreviewIfNeeded();
            }, delay);
        }

        function togglePreviewJointDetails(index, button) {
            const controller = previewJointControllers[index];
            const wrapper = button?.closest('.joint-control');
            if (!controller || !wrapper) return;
            const key = controller.name;
            const expanded = !wrapper.classList.contains('details-expanded');
            wrapper.classList.toggle('details-expanded', expanded);
            button.setAttribute('aria-expanded', expanded ? 'true' : 'false');
            button.title = expanded ? '세부 설정 접기' : '세부 설정 펼치기';
            button.setAttribute(
                'aria-label',
                expanded ? '세부 설정 접기' : '세부 설정 펼치기'
            );
            if (expanded) expandedPreviewJointDetails.add(key);
            else expandedPreviewJointDetails.delete(key);
        }

        function activatePreviewJoint(index, event = null) {
            if (event) {
                event.preventDefault();
                event.stopPropagation();
            }
            const controller = previewJointControllers[index];
            const jointObj = controller?.jointObj;
            const childNode = jointObj?.link_group;
            if (!jointObj || !childNode) return;
            const alreadySelected = selectedElement?.type === 'joint'
                && selectedElement.jointObj === jointObj;
            if (!alreadySelected) {
                selectElement('joint', childNode, jointObj);
                return;
            }
            updateSelectedJointFrameVisibility();
            updatePanel();
            renderPreviewJointControls();
        }

        function renderPreviewJointControls() {
            const container = document.getElementById('joint-controls');
            if (!container) return;
            container.innerHTML = '';

            function getAxisType(axisValues) {
                const [x, y, z] = axisValues;
                if (x === 1 && y === 0 && z === 0) return 'x';
                if (x === -1 && y === 0 && z === 0) return 'nx';
                if (x === 0 && y === 1 && z === 0) return 'y';
                if (x === 0 && y === -1 && z === 0) return 'ny';
                if (x === 0 && y === 0 && z === 1) return 'z';
                if (x === 0 && y === 0 && z === -1) return 'nz';
                return 'custom';
            }

            previewJointControllers.forEach((controller, index) => {
                    if (controller.type === 'fixed') return;
                    const isPrismatic = controller.type === 'prismatic';
                    const isContinuous = controller.type === 'continuous';
                    const lowerWasSet = controller.jointInfo._manual_limit_lower_set === true;
                    const upperWasSet = controller.jointInfo._manual_limit_upper_set === true;
                    const manualLimitPending = controller.type === 'revolute'
                        && (lowerWasSet !== upperWasSet);
                    let min = isPrismatic ? (controller.lowerLimit != null ? controller.lowerLimit : -0.1) : -360;
                    let max = isPrismatic ? (controller.upperLimit != null ? controller.upperLimit : 0.1) : 360;
                    let step = isPrismatic ? 0.001 : 1;

                    if (!isPrismatic && controller.type === 'revolute' && !manualLimitPending) {
                        if (Number.isFinite(controller.lowerLimit)) min = Math.round(controller.lowerLimit * 180 / Math.PI);
                        if (Number.isFinite(controller.upperLimit)) max = Math.round(controller.upperLimit * 180 / Math.PI);
                    }
                    const currentValue = Math.max(min, Math.min(max, Number(controller.value) || 0));
                    const lowerDegrees = Number.isFinite(Number(controller.jointInfo.lower_limit))
                        ? Number(controller.jointInfo.lower_limit) * 180 / Math.PI
                        : null;
                    const upperDegrees = Number.isFinite(Number(controller.jointInfo.upper_limit))
                        ? Number(controller.jointInfo.upper_limit) * 180 / Math.PI
                        : null;
                    const limitIsReady = controller.type === 'revolute'
                        && !manualLimitPending
                        && lowerDegrees !== null
                        && upperDegrees !== null
                        && upperDegrees > lowerDegrees;
                    const limitSummary = controller.type === 'continuous'
                        ? '연속 회전 · 최소/최대 제한 없음'
                        : (
                            limitIsReady
                                ? `허용 범위 ${lowerDegrees.toFixed(1)}° ~ ${upperDegrees.toFixed(1)}°`
                                : `리밋 지정 중 · 최소 ${lowerWasSet ? `${lowerDegrees.toFixed(1)}°` : '미지정'} / 최대 ${upperWasSet ? `${upperDegrees.toFixed(1)}°` : '미지정'}`
                        );
                    const importedLimitReady = controller.type === 'revolute'
                        && !lowerWasSet
                        && !upperWasSet
                        && limitIsReady;
                    const lowerInputValue = (lowerWasSet || importedLimitReady) && lowerDegrees !== null
                        ? Number(lowerDegrees.toFixed(3))
                        : '';
                    const upperInputValue = (upperWasSet || importedLimitReady) && upperDegrees !== null
                        ? Number(upperDegrees.toFixed(3))
                        : '';

                    const axisValues = controller.jointInfo.axis || [0, 0, 1];
                    const axisType = getAxisType(axisValues);
                    const axisCandidates = controller.jointInfo._axis_candidates || [];
                    const axisCandidateOptions = axisCandidates.map((candidate, candidateIndex) => `
                                <option value="${candidateIndex}" ${JSON.stringify(candidate.axis) === JSON.stringify(axisValues) ? 'selected' : ''}>${candidate.label}: [${candidate.axis.join(', ')}]</option>
                            `).join('');

                    const wrapper = document.createElement('div');
                    const detailsExpanded = expandedPreviewJointDetails.has(controller.name);
                    const isSelected = selectedElement?.type === 'joint'
                        && (
                            selectedElement.jointObj === controller.jointObj
                            || selectedElement.jointObj?.joint_name === controller.name
                        );
                    wrapper.className = `joint-control${detailsExpanded ? ' details-expanded' : ''}${isSelected ? ' is-selected' : ''}`;
                    wrapper.innerHTML = `
                        <div class="joint-title">
                            <button type="button" class="joint-name-button"
                                    aria-pressed="${isSelected ? 'true' : 'false'}"
                                    title="${controller.name} 조인트 속성 열기"
                                    onclick="activatePreviewJoint(${index}, event)">${controller.name}</button>
                            <span class="joint-badge-ui">${controller.type}</span>
                        </div>
                        <input class="joint-slider" type="range" min="${min}" max="${max}" step="${step}" value="${currentValue}" data-preview-joint="${index}">
                        <div class="joint-value-row">
                            <span>${min}</span>
                            <div class="joint-fine-control">
                                ${isPrismatic ? '' : `<button type="button" onclick="nudgePreviewJoint(${index}, -1)">−1°</button>`}
                                <input class="joint-value joint-current-input" id="joint-value-${index}"
                                       data-preview-joint-value="${index}" type="number" step="${step}"
                                       value="${Number.isInteger(currentValue) ? currentValue : currentValue.toFixed(3)}"
                                       onchange="commitPreviewJointValue(${index}, this)"
                                       onkeydown="handlePreviewJointValueKey(event, ${index})">
                                ${isPrismatic ? '' : `<button type="button" onclick="nudgePreviewJoint(${index}, 1)">+1°</button>`}
                            </div>
                            <span>${max}</span>
                        </div>
                        ${isContinuous ? '<div class="joint-limit-summary">미리보기 조작 범위 · URDF 회전 제한 아님</div>' : ''}
                        <button type="button" class="joint-details-toggle"
                                aria-expanded="${detailsExpanded ? 'true' : 'false'}"
                                aria-label="${detailsExpanded ? '세부 설정 접기' : '세부 설정 펼치기'}"
                                title="${detailsExpanded ? '세부 설정 접기' : '세부 설정 펼치기'}"
                                onclick="togglePreviewJointDetails(${index}, this)">
                            <span class="joint-details-arrow" aria-hidden="true">
                                <svg viewBox="0 0 12 7">
                                    <path d="M1 1l5 5 5-5" fill="none" stroke="currentColor"
                                          stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>
                                </svg>
                            </span>
                        </button>
                        <div class="joint-details">
                        ${controller.type === 'revolute' ? `
                        <div class="joint-limit-editor">
                            <div class="joint-limit-actions">
                                <button type="button" onclick="setPreviewJointLimit(${index}, 'lower')">현재 ${currentValue}° → 최소</button>
                                <button type="button" onclick="setPreviewJointLimit(${index}, 'upper')">현재 ${currentValue}° → 최대</button>
                            </div>
                            <div class="joint-limit-inputs">
                                <label>최소°
                                    <input type="number" step="0.1" value="${lowerInputValue}"
                                           placeholder="미지정"
                                           onchange="setPreviewJointLimitDegrees(${index}, 'lower', this.value)">
                                </label>
                                <label>최대°
                                    <input type="number" step="0.1" value="${upperInputValue}"
                                           placeholder="미지정"
                                           onchange="setPreviewJointLimitDegrees(${index}, 'upper', this.value)">
                                </label>
                            </div>
                            <div id="joint-limit-summary-${index}" class="joint-limit-summary ${manualLimitPending ? 'pending' : ''}">
                                <span>${limitSummary}</span>
                            </div>
                        </div>` : ''}
                        <div class="joint-axis-row" style="display: grid; grid-template-columns: 1fr 2fr; gap: 8px; margin-top: 6px; align-items: center;">
                            <label style="font-size: 10px; color: #aaa;">Rotation Axis</label>
                            <select class="joint-rpy-input" data-preview-axis-type="${index}">
                                <option value="x" ${axisType === 'x' ? 'selected' : ''}>+X [1, 0, 0]</option>
                                <option value="nx" ${axisType === 'nx' ? 'selected' : ''}>-X [-1, 0, 0]</option>
                                <option value="y" ${axisType === 'y' ? 'selected' : ''}>+Y [0, 1, 0]</option>
                                <option value="ny" ${axisType === 'ny' ? 'selected' : ''}>-Y [0, -1, 0]</option>
                                <option value="z" ${axisType === 'z' ? 'selected' : ''}>+Z [0, 0, 1]</option>
                                <option value="nz" ${axisType === 'nz' ? 'selected' : ''}>-Z [0, 0, -1]</option>
                                <option value="custom" ${axisType === 'custom' ? 'selected' : ''}>Custom</option>
                            </select>
                        </div>
                        <div class="joint-custom-axis-row" id="custom-axis-${index}" style="display: ${axisType === 'custom' ? 'grid' : 'none'}; grid-template-columns: repeat(3, 1fr); gap: 4px; margin-top: 4px;">
                             <input class="joint-rpy-input" type="number" step="0.1" value="${axisValues[0]}" data-preview-axis-val="${index}" data-dim="x" title="Axis X">
                             <input class="joint-rpy-input" type="number" step="0.1" value="${axisValues[1]}" data-preview-axis-val="${index}" data-dim="y" title="Axis Y">
                             <input class="joint-rpy-input" type="number" step="0.1" value="${axisValues[2]}" data-preview-axis-val="${index}" data-dim="z" title="Axis Z">
                        </div>
                        ${axisCandidateOptions ? `
                        <div class="joint-axis-row" style="display: grid; grid-template-columns: 1fr 2fr; gap: 8px; margin-top: 6px; align-items: center;">
                            <label style="font-size: 10px; color: #aaa;">Fusion Candidate</label>
                            <select class="joint-rpy-input" data-preview-axis-candidate="${index}">
                                ${axisCandidateOptions}
                            </select>
                        </div>` : ''}
                        <div style="font-size: 10px; color: #aaa; margin-top: 8px; margin-bottom: 4px;">Joint Origin Orientation (RPY deg)</div>
                        <div class="joint-edit-row">
                            <label>rx<input class="joint-rpy-input" type="number" step="1" value="${((controller.jointInfo._manual_rpy || controller.jointInfo.rpy || [0,0,0])[0] * 180 / Math.PI).toFixed(1)}" data-preview-rpy="${index}" data-axis="0"></label>
                            <label>ry<input class="joint-rpy-input" type="number" step="1" value="${((controller.jointInfo._manual_rpy || controller.jointInfo.rpy || [0,0,0])[1] * 180 / Math.PI).toFixed(1)}" data-preview-rpy="${index}" data-axis="1"></label>
                            <label>rz<input class="joint-rpy-input" type="number" step="1" value="${((controller.jointInfo._manual_rpy || controller.jointInfo.rpy || [0,0,0])[2] * 180 / Math.PI).toFixed(1)}" data-preview-rpy="${index}" data-axis="2"></label>
                        </div>
                        </div>
                    `;
                    container.appendChild(wrapper);
                });

            container.querySelectorAll('[data-preview-joint]').forEach(input => {
                input.addEventListener('pointerdown', event => {
                    beginPreviewJointGesture(Number(event.target.dataset.previewJoint));
                });
                input.addEventListener('focus', event => {
                    beginPreviewJointGesture(Number(event.target.dataset.previewJoint));
                });
                input.addEventListener('input', event => {
                    const controllerIndex = Number(event.target.dataset.previewJoint);
                    setPreviewJointValue(controllerIndex, Number(event.target.value));
                });
                input.addEventListener('change', event => {
                    endPreviewJointGesture(Number(event.target.dataset.previewJoint));
                });
                input.addEventListener('blur', event => {
                    endPreviewJointGesture(Number(event.target.dataset.previewJoint));
                });
                input.addEventListener('wheel', event => {
                    const controllerIndex = Number(event.target.dataset.previewJoint);
                    const controller = previewJointControllers[controllerIndex];
                    if (!controller || controller.type === 'prismatic') return;
                    event.preventDefault();
                    nudgePreviewJoint(controllerIndex, event.deltaY < 0 ? 1 : -1);
                }, { passive: false });
            });

            container.querySelectorAll('[data-preview-rpy]').forEach(input => {
                input.addEventListener('change', event => {
                    const controllerIndex = Number(event.target.dataset.previewRpy);
                    const axisIndex = Number(event.target.dataset.axis);
                    setPreviewJointRpy(controllerIndex, axisIndex, Number(event.target.value));
                });
            });

            container.querySelectorAll('[data-preview-axis-type]').forEach(select => {
                select.addEventListener('change', event => {
                    const controllerIndex = Number(event.target.dataset.previewAxisType);
                    const type = event.target.value;
                    setPreviewJointAxisType(controllerIndex, type);
                });
            });

            container.querySelectorAll('[data-preview-axis-val]').forEach(input => {
                input.addEventListener('change', event => {
                    const controllerIndex = Number(event.target.dataset.previewAxisVal);
                    const dim = event.target.dataset.dim;
                    const val = Number(event.target.value);
                    setPreviewJointAxisVal(controllerIndex, dim, val);
                });
            });

            container.querySelectorAll('[data-preview-axis-candidate]').forEach(select => {
                select.addEventListener('change', event => {
                    const controllerIndex = Number(event.target.dataset.previewAxisCandidate);
                    setPreviewJointAxisCandidate(controllerIndex, Number(event.target.value));
                });
            });
        }

        function setPreviewJointAxisType(index, type) {
            const controller = previewJointControllers[index];
            if (!controller || !controller.jointObj) return;
            let axis = [0, 0, 1];
            if (type === 'x') axis = [1, 0, 0];
            else if (type === 'nx') axis = [-1, 0, 0];
            else if (type === 'y') axis = [0, 1, 0];
            else if (type === 'ny') axis = [0, -1, 0];
            else if (type === 'z') axis = [0, 0, 1];
            else if (type === 'nz') axis = [0, 0, -1];
            else {
                axis = (controller.jointInfo && controller.jointInfo.axis) || [1, 0, 0];
            }

            const customRow = document.getElementById(`custom-axis-${index}`);
            if (customRow) customRow.style.display = (type === 'custom') ? 'grid' : 'none';

            if (type === 'custom') {
                const inputs = customRow.querySelectorAll('input');
                inputs[0].value = axis[0];
                inputs[1].value = axis[1];
                inputs[2].value = axis[2];
            }

            applyJointAxisChange(controller.jointObj, axis, `preview_axis_${type}`);
        }

        function setPreviewJointAxisVal(index, dim, val) {
            const controller = previewJointControllers[index];
            if (!controller || !controller.jointObj) return;
            const axis = ((controller.jointInfo && controller.jointInfo.axis) || [0, 0, 1]).slice();
            if (dim === 'x') axis[0] = Number(val);
            else if (dim === 'y') axis[1] = Number(val);
            else if (dim === 'z') axis[2] = Number(val);
            applyJointAxisChange(controller.jointObj, axis, 'preview_custom_axis');
        }

        function setPreviewJointAxisCandidate(index, candidateIndex) {
            const controller = previewJointControllers[index];
            if (!controller || !controller.jointObj || !controller.jointInfo) return;
            const candidate = (controller.jointInfo._axis_candidates || [])[candidateIndex];
            if (!candidate) return;
            applyJointAxisChange(controller.jointObj, candidate.axis.slice(), candidate.label);
        }

        function setPreviewJointRpy(index, axisIndex, degrees) {
            const controller = previewJointControllers[index];
            if (!controller || !controller.jointInfo || !Number.isFinite(degrees)) return;
            saveState();
            const rpy = (controller.jointInfo._manual_rpy || controller.jointInfo.rpy || [0, 0, 0]).slice();
            rpy[axisIndex] = degrees * Math.PI / 180;
            controller.jointInfo._manual_rpy = rpy;
            controller.jointInfo.rpy = rpy;
            
            // Update base quaternion directly so the mesh rotates with the joint frame
            const euler = new THREE.Euler(rpy[0], rpy[1], rpy[2], 'ZYX');
            controller.baseQuaternion.setFromEuler(euler);
            controller.jointInfo._preview_local_quaternion = controller.baseQuaternion.toArray();
            delete controller.jointInfo._preview_world_quaternion;
            delete controller.jointInfo._preview_world_frame_matrix;
            
            // Re-apply the current slider value to visually rotate the mesh immediately
            setPreviewJointValue(index, controller.value);
        }

        function setPreviewJointLimit(index, bound) {
            const controller = previewJointControllers[index];
            if (!controller || controller.type === 'fixed' || controller.type === 'prismatic') return false;
            const currentDegrees = Number(controller.value);
            if (!Number.isFinite(currentDegrees)) return false;
            return applyPreviewJointLimitDegrees(index, bound, currentDegrees);
        }

        function setPreviewJointLimitDegrees(index, bound, degrees) {
            if (String(degrees).trim() === '') {
                const summary = document.getElementById(`joint-limit-summary-${index}`);
                if (summary) {
                    summary.classList.add('pending');
                    summary.textContent = '최소·최대 각도에는 숫자를 입력하세요.';
                }
                return false;
            }
            const parsedDegrees = Number(degrees);
            if (!Number.isFinite(parsedDegrees)) {
                const summary = document.getElementById(`joint-limit-summary-${index}`);
                if (summary) {
                    summary.classList.add('pending');
                    summary.textContent = '최소·최대 각도에는 숫자를 입력하세요.';
                }
                return false;
            }
            return applyPreviewJointLimitDegrees(index, bound, parsedDegrees);
        }

        function applyPreviewJointLimitDegrees(index, bound, degrees) {
            const controller = previewJointControllers[index];
            if (!controller || controller.type === 'fixed' || controller.type === 'prismatic') return false;
            const currentRadians = degrees * Math.PI / 180;
            const jointInfo = controller.jointInfo;
            const existingLower = Number(jointInfo.lower_limit);
            const existingUpper = Number(jointInfo.upper_limit);
            const hasExistingRevoluteRange = controller.type === 'revolute'
                && jointInfo._manual_limit_lower_set !== true
                && jointInfo._manual_limit_upper_set !== true
                && Number.isFinite(existingLower)
                && Number.isFinite(existingUpper)
                && existingUpper > existingLower;
            const lowerWasSet = jointInfo._manual_limit_lower_set === true
                || hasExistingRevoluteRange;
            const upperWasSet = jointInfo._manual_limit_upper_set === true
                || hasExistingRevoluteRange;

            if (bound === 'lower' && upperWasSet && currentRadians >= existingUpper - 1e-9) {
                const summary = document.getElementById(`joint-limit-summary-${index}`);
                if (summary) {
                    summary.classList.add('pending');
                    summary.textContent = '최소각은 설정된 최대각보다 작아야 합니다.';
                }
                return false;
            }
            if (bound === 'upper' && lowerWasSet && currentRadians <= existingLower + 1e-9) {
                const summary = document.getElementById(`joint-limit-summary-${index}`);
                if (summary) {
                    summary.classList.add('pending');
                    summary.textContent = '최대각은 설정된 최소각보다 커야 합니다.';
                }
                return false;
            }

            saveState();
            if (controller.type === 'continuous') {
                controller.type = 'revolute';
                if (controller.jointObj) controller.jointObj.joint_type = 'revolute';
                jointInfo.type = 'revolute';
            }
            jointInfo.provenance = 'user_visual_joint_limit';
            if (hasExistingRevoluteRange) {
                jointInfo._manual_limit_lower_set = true;
                jointInfo._manual_limit_upper_set = true;
            }
            if (bound === 'lower') {
                jointInfo.lower_limit = currentRadians;
                jointInfo._manual_limit_lower_set = true;
                if (!Number.isFinite(existingUpper) || existingUpper <= currentRadians) {
                    jointInfo.upper_limit = Math.max(2 * Math.PI, currentRadians + Math.PI / 180);
                }
            } else {
                jointInfo.upper_limit = currentRadians;
                jointInfo._manual_limit_upper_set = true;
                if (!Number.isFinite(existingLower) || existingLower >= currentRadians) {
                    jointInfo.lower_limit = Math.min(-2 * Math.PI, currentRadians - Math.PI / 180);
                }
            }
            controller.lowerLimit = jointInfo.lower_limit;
            controller.upperLimit = jointInfo.upper_limit;
            let nextValue = Number(controller.value) || 0;
            if (
                jointInfo._manual_limit_lower_set === true
                && jointInfo._manual_limit_upper_set === true
                && jointInfo.upper_limit > jointInfo.lower_limit
            ) {
                const lowerDegrees = jointInfo.lower_limit * 180 / Math.PI;
                const upperDegrees = jointInfo.upper_limit * 180 / Math.PI;
                nextValue = Math.max(lowerDegrees, Math.min(upperDegrees, nextValue));
            }
            render({ skipPreview: true });
            renderPreviewJointControls();
            setPreviewJointValue(index, nextValue);
            return true;
        }

        function previewJointValueText(value) {
            return Number.isInteger(value) ? String(value) : Number(value).toFixed(3);
        }

        function commitPreviewJointValue(index, input) {
            const controller = previewJointControllers[index];
            if (!controller || !input) return false;
            const previousValue = Number(controller.value) || 0;
            let value = Number(input.value);
            if (!Number.isFinite(value)) {
                input.value = previewJointValueText(Number(controller.value) || 0);
                return false;
            }
            const localControl = input.closest('.joint-control');
            const slider = localControl
                ? localControl.querySelector(`[data-preview-joint="${index}"]`)
                : document.querySelector(`[data-preview-joint="${index}"]`);
            if (slider) {
                const min = Number(slider.min);
                const max = Number(slider.max);
                if (Number.isFinite(min)) value = Math.max(min, value);
                if (Number.isFinite(max)) value = Math.min(max, value);
            }
            input.value = previewJointValueText(value);
            if (Math.abs(value - previousValue) > 1e-9) {
                pushHistoryEntry({
                    kind: 'preview_joint',
                    jointName: controller.name,
                    value: previousValue,
                });
            }
            setPreviewJointValue(index, value);
            return true;
        }

        function handlePreviewJointValueKey(event, index) {
            if (event.key === 'Enter') {
                event.preventDefault();
                commitPreviewJointValue(index, event.target);
                event.target.blur();
            } else if (event.key === 'Escape') {
                event.preventDefault();
                const controller = previewJointControllers[index];
                event.target.value = previewJointValueText(
                    controller ? Number(controller.value) || 0 : 0
                );
                event.target.blur();
            }
        }

        function setPreviewJointValue(index, value) {
            const controller = previewJointControllers[index];
            if (!controller) return;
            controller.value = value;
            if (controller.jointInfo) {
                controller.jointInfo.initial_position = controller.type === 'prismatic'
                    ? Number(value)
                    : THREE.MathUtils.degToRad(Number(value));
            }
            if (treeData) {
                treeData._preview_joint_positions = treeData._preview_joint_positions || {};
                treeData._preview_joint_positions[controller.name] = Number(value) || 0;
            }
            controller.pivot.position.copy(controller.basePosition);
            controller.pivot.quaternion.copy(controller.baseQuaternion);

            if (controller.type === 'prismatic') {
                const offset = controller.axis.clone().multiplyScalar(value * controller.unitsPerMeter);
                // The prismatic axis is in the joint frame, so we need to rotate it by the base rotation
                offset.applyQuaternion(controller.baseQuaternion);
                controller.pivot.position.add(offset);
            } else if (controller.type !== 'fixed') {
                const angleRad = value * Math.PI / 180;
                const rotation = new THREE.Quaternion().setFromAxisAngle(controller.axis, angleRad);
                controller.pivot.quaternion.multiply(rotation);
            }

            document.querySelectorAll(`[data-preview-joint-value="${index}"]`).forEach(valueEl => {
                if (document.activeElement !== valueEl) {
                    valueEl.value = previewJointValueText(value);
                }
            });
            document.querySelectorAll(`[data-preview-joint="${index}"]`).forEach(slider => {
                if (document.activeElement !== slider) slider.value = value;
            });
            document.querySelectorAll(`[data-set-joint-zero="${index}"]`).forEach(button => {
                const numericValue = Number(value) || 0;
                const unit = controller.type === 'prismatic' ? ' m' : '°';
                button.disabled = Math.abs(numericValue) <= 1e-9;
                button.textContent = `현재 ${previewJointValueText(numericValue)}${unit} 자세를 0으로 설정`;
            });
        }

        function shiftJointLimitsForNewZero(jointInfo, jointType, zeroOffset) {
            if (!jointInfo || jointType === 'continuous') return;
            ['lower_limit', 'upper_limit'].forEach(key => {
                const value = Number(jointInfo[key]);
                if (Number.isFinite(value)) jointInfo[key] = value - zeroOffset;
            });
        }

        function shiftMimicOffsetsForNewZero(jointObj, zeroOffset) {
            if (!treeData || !jointObj || !Number.isFinite(zeroOffset)) return;
            const ownInfo = jointObj.joint_info || {};
            if (ownInfo.mimic_joint) {
                ownInfo.mimic_offset = Number(ownInfo.mimic_offset || 0) - zeroOffset;
            }
            getFlatLinks(treeData, null, -1).forEach(item => {
                const candidate = item.jointObj;
                if (!candidate || candidate === jointObj) return;
                const candidateInfo = candidate.joint_info || {};
                if (candidateInfo.mimic_joint !== jointObj.joint_name) return;
                const multiplier = Number.isFinite(Number(candidateInfo.mimic_multiplier))
                    ? Number(candidateInfo.mimic_multiplier)
                    : 1;
                candidateInfo.mimic_offset = Number(candidateInfo.mimic_offset || 0)
                    + multiplier * zeroOffset;
            });
        }

        function updateStoredJointWorldFrame(jointInfo, worldFrame, unitsPerMeter) {
            if (!jointInfo || !worldFrame) return;
            const position = new THREE.Vector3();
            const quaternion = new THREE.Quaternion();
            const scale = new THREE.Vector3();
            worldFrame.decompose(position, quaternion, scale);
            jointInfo._preview_world_frame_matrix = worldFrame.toArray();
            jointInfo._preview_world_xyz = position.clone()
                .divideScalar(unitsPerMeter)
                .toArray();
            jointInfo._preview_world_quaternion = quaternion.normalize().toArray();
            if (!jointInfo._joint_snap) return;
            const snap = jointInfo._joint_snap;
            snap.root_point = position.toArray();
            snap.root_tangent = new THREE.Vector3()
                .setFromMatrixColumn(worldFrame, 0).normalize().toArray();
            snap.root_y_axis = new THREE.Vector3()
                .setFromMatrixColumn(worldFrame, 1).normalize().toArray();
            snap.root_normal = new THREE.Vector3()
                .setFromMatrixColumn(worldFrame, 2).normalize().toArray();
            snap.zero_calibrated = true;
        }

        function applyJointZeroDeltaToSubtree(node, worldDelta, unitsPerMeter) {
            if (!node || !worldDelta || !treeData) return;
            treeData._preview_transforms = treeData._preview_transforms || {};
            (node.components || []).forEach(component => {
                const values = treeData._preview_transforms[component];
                if (!Array.isArray(values) || values.length !== 16) return;
                const transformed = worldDelta.clone().multiply(
                    new THREE.Matrix4().fromArray(values)
                );
                treeData._preview_transforms[component] = transformed.toArray();
            });
            (node.children || []).forEach(child => {
                const childInfo = child.joint_info || {};
                const values = childInfo._preview_world_frame_matrix;
                if (Array.isArray(values) && values.length === 16) {
                    const transformed = worldDelta.clone().multiply(
                        new THREE.Matrix4().fromArray(values)
                    );
                    updateStoredJointWorldFrame(childInfo, transformed, unitsPerMeter);
                }
                applyJointZeroDeltaToSubtree(child.link_group, worldDelta, unitsPerMeter);
            });
        }

        function previewControllerZeroWorldFrame(controller) {
            if (!controller || !controller.pivot || !controller.pivot.parent || !robotRoot) {
                return null;
            }
            robotRoot.updateMatrixWorld(true);
            controller.pivot.parent.updateMatrixWorld(true);
            const baseLocalFrame = new THREE.Matrix4().compose(
                controller.basePosition.clone(),
                controller.baseQuaternion.clone(),
                new THREE.Vector3(1, 1, 1)
            );
            return robotRoot.matrixWorld.clone().invert()
                .multiply(controller.pivot.parent.matrixWorld)
                .multiply(baseLocalFrame);
        }

        function previewControllerNeutralZeroWorldFrame(controller, entry) {
            const posedZeroFrame = previewControllerZeroWorldFrame(controller);
            if (!posedZeroFrame || !entry || !entry.parentNode || entry.parentNode === treeData) {
                return posedZeroFrame;
            }
            const parentPivot = entry.parentNode._pivot;
            if (!parentPivot || !robotRoot) return posedZeroFrame;

            robotRoot.updateMatrixWorld(true);
            parentPivot.updateMatrixWorld(true);
            const posedParentFrame = robotRoot.matrixWorld.clone().invert()
                .multiply(parentPivot.matrixWorld);
            const neutralParentFrame = previewFrameMatrixForNode(entry.parentNode);
            const parentPoseDelta = posedParentFrame.clone()
                .multiply(neutralParentFrame.clone().invert());

            // The live pivot sits below every currently posed ancestor. Remove
            // that accumulated parent motion before using it as a stored frame;
            // otherwise the ancestor pose is baked into the joint origin and
            // then applied a second time when the rig is rebuilt.
            return parentPoseDelta.invert().multiply(posedZeroFrame);
        }

        function cloneJsonValue(value) {
            return value === undefined ? undefined : JSON.parse(JSON.stringify(value));
        }

        function setPreviewJointZero(index) {
            const controller = previewJointControllers[index];
            if (!controller || controller.type === 'fixed' || !controller.jointObj) return false;
            const displayedOffset = Number(controller.value) || 0;
            if (Math.abs(displayedOffset) <= 1e-9) return false;

            const joint = controller.jointObj;
            const jointInfo = controller.jointInfo || joint.joint_info || {};
            const entry = jointEntryFor(joint);
            if (!entry) return false;

            saveState();
            const parentFrame = previewFrameMatrixForNode(entry.parentNode);
            const storedWorldValues = jointInfo._preview_world_frame_matrix;
            // Stored component transforms are the neutral CAD pose, so the
            // joint frame used to bake a new zero must be neutral as well.
            // A live pivot is below posed ancestors (joint_3 is commonly near
            // 160 degrees here); preferring it would bake that ancestor pose
            // into joint_4 and apply it again on the next rig rebuild.
            const previousWorldFrame = (
                Array.isArray(storedWorldValues) && storedWorldValues.length === 16
                    ? new THREE.Matrix4().fromArray(storedWorldValues)
                    : previewControllerNeutralZeroWorldFrame(controller, entry)
            ) || parentFrame.clone().multiply(
                    new THREE.Matrix4().compose(
                        controller.basePosition.clone(),
                        controller.baseQuaternion.clone(),
                        new THREE.Vector3(1, 1, 1)
                    )
                );
            const axis = controller.axis.clone().normalize();
            const jointMotion = controller.type === 'prismatic'
                ? new THREE.Matrix4().makeTranslation(
                    axis.x * displayedOffset * controller.unitsPerMeter,
                    axis.y * displayedOffset * controller.unitsPerMeter,
                    axis.z * displayedOffset * controller.unitsPerMeter
                )
                : new THREE.Matrix4().makeRotationAxis(
                    axis,
                    THREE.MathUtils.degToRad(displayedOffset)
                );
            // Build the new zero from the neutral zero frame. The resulting
            // delta can safely be applied to neutral component transforms.
            const worldZeroFrame = previousWorldFrame.clone().multiply(jointMotion);
            const localZeroFrame = parentFrame.clone().invert().multiply(worldZeroFrame);
            const worldDelta = worldZeroFrame.clone().multiply(previousWorldFrame.clone().invert());
            const localPosition = new THREE.Vector3();
            const localQuaternion = new THREE.Quaternion();
            const localScale = new THREE.Vector3();
            localZeroFrame.decompose(localPosition, localQuaternion, localScale);
            const localRpy = new THREE.Euler().setFromQuaternion(localQuaternion, 'ZYX');
            const unitsPerMeter = Number(controller.unitsPerMeter) || 1000.0;
            const zeroOffset = controller.type === 'prismatic'
                ? displayedOffset
                : THREE.MathUtils.degToRad(displayedOffset);

            const mimicOffsets = {};
            getFlatLinks(treeData, null, -1).forEach(item => {
                const candidate = item.jointObj;
                const candidateInfo = candidate && candidate.joint_info;
                if (!candidateInfo || candidateInfo.mimic_joint !== joint.joint_name) return;
                mimicOffsets[candidate.joint_name] = candidateInfo.mimic_offset;
            });
            jointInfo._zero_calibration_backup = {
                world_delta_matrix: worldDelta.toArray(),
                previous_world_frame_matrix: cloneJsonValue(storedWorldValues),
                previous_world_xyz: cloneJsonValue(jointInfo._preview_world_xyz),
                previous_world_quaternion: cloneJsonValue(jointInfo._preview_world_quaternion),
                previous_joint_snap: cloneJsonValue(jointInfo._joint_snap),
                previous_initial_position: jointInfo.initial_position,
                previous_lower_limit: jointInfo.lower_limit,
                previous_upper_limit: jointInfo.upper_limit,
                previous_provenance: jointInfo.provenance,
                previous_zero_offset_calibration: jointInfo._zero_offset_calibration,
                mimic_offsets: mimicOffsets,
            };

            joint.joint_info = jointInfo;
            jointInfo.xyz = localPosition.clone().divideScalar(unitsPerMeter).toArray();
            jointInfo.rpy = [localRpy.x, localRpy.y, localRpy.z];
            jointInfo._manual_rpy = jointInfo.rpy.slice();
            jointInfo._preview_local_quaternion = localQuaternion.normalize().toArray();
            updateStoredJointWorldFrame(jointInfo, worldZeroFrame, unitsPerMeter);
            jointInfo.initial_position = 0;
            jointInfo._zero_offset_calibration = Number(
                jointInfo._zero_offset_calibration || 0
            ) + zeroOffset;
            jointInfo.provenance = 'user_zero_calibrated';

            shiftJointLimitsForNewZero(jointInfo, controller.type, zeroOffset);
            shiftMimicOffsetsForNewZero(joint, zeroOffset);
            applyJointZeroDeltaToSubtree(entry.node, worldDelta, unitsPerMeter);
            treeData._preview_joint_positions = treeData._preview_joint_positions || {};
            treeData._preview_joint_positions[joint.joint_name] = 0;
            syncPickedJointLocalFrames();

            previewRigDirty = true;
            previewControlsDirty = true;
            refreshPreviewRig();
            render({ skipPreview: true });
            updateSelectedJointFrameVisibility();

            const status = document.getElementById('viewer-pick-status');
            if (status) {
                const unit = controller.type === 'prismatic' ? 'm' : '°';
                status.textContent = `${joint.joint_name}: 기존 ${displayedOffset}${unit} 자세를 새 0으로 설정했습니다.`;
                status.style.display = 'block';
            }
            return true;
        }

        function revertPreviewJointZero(index) {
            const controller = previewJointControllers[index];
            if (!controller || controller.type === 'fixed' || !controller.jointObj) return false;
            const joint = controller.jointObj;
            const jointInfo = controller.jointInfo || joint.joint_info || {};
            const zeroOffset = Number(jointInfo._zero_offset_calibration);
            const storedWorldValues = jointInfo._preview_world_frame_matrix;
            const backup = jointInfo._zero_calibration_backup;
            const entry = jointEntryFor(joint);
            if (
                !Number.isFinite(zeroOffset)
                || Math.abs(zeroOffset) <= 1e-12
                || !Array.isArray(storedWorldValues)
                || storedWorldValues.length !== 16
                || !entry
            ) return false;

            saveState();
            const unitsPerMeter = Number(controller.unitsPerMeter) || 1000.0;
            const axis = controller.axis.clone().normalize();
            const bakedMotion = controller.type === 'prismatic'
                ? new THREE.Matrix4().makeTranslation(
                    axis.x * zeroOffset * unitsPerMeter,
                    axis.y * zeroOffset * unitsPerMeter,
                    axis.z * zeroOffset * unitsPerMeter
                )
                : new THREE.Matrix4().makeRotationAxis(axis, zeroOffset);
            const currentWorldFrame = new THREE.Matrix4().fromArray(storedWorldValues);
            const previousWorldFrame = Array.isArray(backup?.previous_world_frame_matrix)
                && backup.previous_world_frame_matrix.length === 16
                ? new THREE.Matrix4().fromArray(backup.previous_world_frame_matrix)
                : currentWorldFrame.clone().multiply(bakedMotion.clone().invert());
            const reverseWorldDelta = Array.isArray(backup?.world_delta_matrix)
                && backup.world_delta_matrix.length === 16
                ? new THREE.Matrix4().fromArray(backup.world_delta_matrix).invert()
                : previousWorldFrame.clone().multiply(currentWorldFrame.clone().invert());
            const parentFrame = previewFrameMatrixForNode(entry.parentNode);
            const previousLocalFrame = parentFrame.clone().invert().multiply(previousWorldFrame);
            const localPosition = new THREE.Vector3();
            const localQuaternion = new THREE.Quaternion();
            const localScale = new THREE.Vector3();
            previousLocalFrame.decompose(localPosition, localQuaternion, localScale);
            const localRpy = new THREE.Euler().setFromQuaternion(localQuaternion, 'ZYX');

            jointInfo.xyz = localPosition.clone().divideScalar(unitsPerMeter).toArray();
            jointInfo.rpy = [localRpy.x, localRpy.y, localRpy.z];
            jointInfo._manual_rpy = jointInfo.rpy.slice();
            jointInfo._preview_local_quaternion = localQuaternion.normalize().toArray();
            updateStoredJointWorldFrame(jointInfo, previousWorldFrame, unitsPerMeter);
            if (backup && Object.prototype.hasOwnProperty.call(backup, 'previous_joint_snap')) {
                if (backup.previous_joint_snap === undefined) delete jointInfo._joint_snap;
                else jointInfo._joint_snap = cloneJsonValue(backup.previous_joint_snap);
            }
            const currentInitial = Number(jointInfo.initial_position) || 0;
            jointInfo.initial_position = backup
                && Object.prototype.hasOwnProperty.call(backup, 'previous_initial_position')
                ? backup.previous_initial_position
                : currentInitial + zeroOffset;
            if (backup) {
                jointInfo.lower_limit = backup.previous_lower_limit;
                jointInfo.upper_limit = backup.previous_upper_limit;
                Object.entries(backup.mimic_offsets || {}).forEach(([name, value]) => {
                    const candidate = getFlatLinks(treeData, null, -1)
                        .map(item => item.jointObj)
                        .find(item => item && item.joint_name === name);
                    if (!candidate || !candidate.joint_info) return;
                    if (value === undefined) delete candidate.joint_info.mimic_offset;
                    else candidate.joint_info.mimic_offset = value;
                });
            } else {
                shiftJointLimitsForNewZero(jointInfo, controller.type, -zeroOffset);
                shiftMimicOffsetsForNewZero(joint, -zeroOffset);
            }
            applyJointZeroDeltaToSubtree(entry.node, reverseWorldDelta, unitsPerMeter);
            if (backup && backup.previous_zero_offset_calibration !== undefined) {
                jointInfo._zero_offset_calibration = backup.previous_zero_offset_calibration;
            } else {
                delete jointInfo._zero_offset_calibration;
            }
            jointInfo.provenance = backup?.previous_provenance || (
                jointInfo._joint_snap
                    ? 'user_3d_joint_pick'
                    : 'user_zero_calibration_reverted'
            );
            delete jointInfo._zero_calibration_backup;
            treeData._preview_joint_positions = treeData._preview_joint_positions || {};
            treeData._preview_joint_positions[joint.joint_name] = controller.type === 'prismatic'
                ? jointInfo.initial_position
                : THREE.MathUtils.radToDeg(jointInfo.initial_position);
            syncPickedJointLocalFrames();

            previewRigDirty = true;
            previewControlsDirty = true;
            refreshPreviewRig();
            render({ skipPreview: true });
            updateSelectedJointFrameVisibility();
            const status = document.getElementById('viewer-pick-status');
            if (status) {
                status.textContent = `${joint.joint_name}: 영점 재설정을 취소하고 직전 좌표계로 복원했습니다.`;
                status.style.display = 'block';
            }
            return true;
        }

        function applyJointAxisChange(jointObj, targetAxis, sourceLabel = null) {
            if (!jointObj || !Array.isArray(targetAxis) || targetAxis.length !== 3) return false;
            const jointInfo = jointObj.joint_info || {};
            jointObj.joint_info = jointInfo;

            const oldAxis = Array.isArray(jointInfo.axis) && jointInfo.axis.length === 3
                ? jointInfo.axis.map(Number)
                : [0, 0, 1];
            let newAxis = targetAxis.map(v => Number(v) || 0);
            const len = Math.hypot(...newAxis);
            if (len <= 1e-9) {
                newAxis = [0, 0, 1];
            } else {
                newAxis = [newAxis[0] / len, newAxis[1] / len, newAxis[2] / len];
            }

            const oldLen = Math.hypot(...oldAxis) || 1;
            const dot = (oldAxis[0] * newAxis[0] + oldAxis[1] * newAxis[1] + oldAxis[2] * newAxis[2]) / oldLen;
            const isOpposite = Math.abs(dot + 1.0) < 1e-4;
            const isSame = Math.abs(dot - 1.0) < 1e-4;

            if (isSame && (!sourceLabel || jointInfo._axis_source === sourceLabel)) {
                return false;
            }

            saveState();

            const controllerIndex = previewJointControllers.findIndex(c => c.jointObj === jointObj);
            const controller = controllerIndex >= 0 ? previewJointControllers[controllerIndex] : null;

            if (isOpposite) {
                // FLIP: 물리적 자세 보존 (시각적/기하학적 자세가 화면 밖으로 튀지 않도록 부호 반전)
                jointInfo.axis = newAxis;
                if (sourceLabel) jointInfo._axis_source = sourceLabel;

                if (jointInfo.initial_position !== undefined) {
                    jointInfo.initial_position = -Number(jointInfo.initial_position || 0);
                }
                if (jointInfo._zero_offset_calibration !== undefined) {
                    jointInfo._zero_offset_calibration = -Number(jointInfo._zero_offset_calibration || 0);
                }
                if (jointInfo.lower_limit !== undefined && jointInfo.upper_limit !== undefined) {
                    const oldLower = Number(jointInfo.lower_limit);
                    const oldUpper = Number(jointInfo.upper_limit);
                    jointInfo.lower_limit = -oldUpper;
                    jointInfo.upper_limit = -oldLower;
                }
                if (controller) {
                    controller.value = -Number(controller.value || 0);
                    controller.axis.set(newAxis[0], newAxis[1], newAxis[2]);
                    if (jointInfo.lower_limit !== undefined) controller.lowerLimit = jointInfo.lower_limit;
                    if (jointInfo.upper_limit !== undefined) controller.upperLimit = jointInfo.upper_limit;
                }
                if (treeData && treeData._preview_joint_positions && treeData._preview_joint_positions[jointObj.joint_name] !== undefined) {
                    treeData._preview_joint_positions[jointObj.joint_name] = -Number(treeData._preview_joint_positions[jointObj.joint_name] || 0);
                }
            } else {
                // 직교/임의 방향으로 축 변경:
                // 이미 영점 보정이 되어 있는 관절인 경우, 구 축 기준 베이크된 변환과의 충돌을 방지하기 위해
                // 백업이 있으면 revertPreviewJointZero를 먼저 호출하여 메쉬와 좌표계를 원상 복구한 후 축을 변경
                if (jointInfo._zero_calibration_backup && controllerIndex >= 0) {
                    revertPreviewJointZero(controllerIndex);
                }
                jointInfo.axis = newAxis;
                if (sourceLabel) jointInfo._axis_source = sourceLabel;
                jointInfo.initial_position = 0;
                if (controller) {
                    controller.value = 0;
                    controller.axis.set(newAxis[0], newAxis[1], newAxis[2]);
                }
                if (treeData && treeData._preview_joint_positions) {
                    treeData._preview_joint_positions[jointObj.joint_name] = 0;
                }
            }

            previewRigDirty = true;
            previewControlsDirty = true;
            render({ previewDelay: 40 });

            const status = document.getElementById('viewer-pick-status');
            if (status) {
                const axisStr = newAxis.map(v => Number(v.toFixed(3))).join(', ');
                status.textContent = `${jointObj.joint_name}: 회전/이동축을 [${axisStr}]로 변경했습니다.${isOpposite ? ' (물리적 자세 보존)' : ''}`;
                status.style.display = 'block';
            }
            return true;
        }

        function capturePreviewJointPose() {
            const pose = {};
            previewJointControllers.forEach(controller => {
                if (controller.type === 'fixed') return;
                pose[controller.name] = Number(controller.value) || 0;
            });
            return pose;
        }

        function restorePreviewJointPose(pose) {
            if (!pose || typeof pose !== 'object') return;
            previewJointControllers.forEach((controller, index) => {
                if (!Object.prototype.hasOwnProperty.call(pose, controller.name)) return;
                setPreviewJointValue(index, Number(pose[controller.name]) || 0);
            });
        }

        function previewJointPosesEqual(first, second) {
            const keys = new Set([
                ...Object.keys(first || {}),
                ...Object.keys(second || {}),
            ]);
            return Array.from(keys).every(
                key => Math.abs(Number(first?.[key] || 0) - Number(second?.[key] || 0)) <= 1e-9
            );
        }

        function beginPreviewJointGesture(index) {
            const controller = previewJointControllers[index];
            if (!controller || controller.type === 'fixed') return;
            if (previewJointGesture?.index === index) return;
            previewJointGesture = {
                index,
                jointName: controller.name,
                value: Number(controller.value) || 0,
            };
        }

        function endPreviewJointGesture(index) {
            if (!previewJointGesture || previewJointGesture.index !== index) return;
            const before = previewJointGesture;
            previewJointGesture = null;
            const controller = previewJointControllers[index];
            if (!controller) return;
            if (Math.abs((Number(controller.value) || 0) - before.value) <= 1e-9) return;
            pushHistoryEntry({
                kind: 'preview_joint',
                jointName: before.jointName,
                value: before.value,
            });
        }

        function nudgePreviewJoint(index, degrees, recordHistory = true) {
            const controller = previewJointControllers[index];
            const slider = document.querySelector(`[data-preview-joint="${index}"]`);
            if (!controller || !slider || controller.type === 'prismatic') return false;
            const min = Number(slider.min);
            const max = Number(slider.max);
            const current = Math.round(Number(controller.value) || 0);
            const next = Math.max(min, Math.min(max, current + Number(degrees)));
            if (next === current) return false;
            if (recordHistory && previewJointGesture?.index !== index) {
                pushHistoryEntry({
                    kind: 'preview_joint',
                    jointName: controller.name,
                    value: Number(controller.value) || 0,
                });
            }
            slider.value = next;
            setPreviewJointValue(index, next);
            return true;
        }

        function resetPreviewJoints() {
            const previousPose = capturePreviewJointPose();
            previewJointControllers.forEach((controller, index) => {
                setPreviewJointValue(index, 0);
                const input = document.querySelector(`[data-preview-joint="${index}"]`);
                if (input) input.value = 0;
            });
            const nextPose = capturePreviewJointPose();
            if (!previewJointPosesEqual(previousPose, nextPose)) {
                pushHistoryEntry({kind: 'preview_pose', pose: previousPose});
            }
        }

        function restoreImportedAssemblyPose(showStatus = true) {
            resetPreviewJoints();
            if (!showStatus) return;
            const viewerStatus = document.getElementById('viewer-pick-status');
            if (viewerStatus) {
                viewerStatus.textContent = '조립품을 처음 불러온 원래 자세로 복원했습니다.';
                viewerStatus.style.display = 'block';
            }
        }

        function randomizePreviewJoints() {
            const previousPose = capturePreviewJointPose();
            previewJointControllers.forEach((controller, index) => {
                if (controller.type === 'fixed') return;
                const input = document.querySelector(`[data-preview-joint="${index}"]`);
                if (!input) return;
                const min = Number(input.min);
                const max = Number(input.max);
                const value = min + Math.random() * (max - min);
                const snapped = controller.type === 'prismatic' ? Number(value.toFixed(3)) : Math.round(value);
                input.value = snapped;
                setPreviewJointValue(index, snapped);
            });
            const nextPose = capturePreviewJointPose();
            if (!previewJointPosesEqual(previousPose, nextPose)) {
                pushHistoryEntry({kind: 'preview_pose', pose: previousPose});
            }
        }

        function applyViewerIsolationVisibility() {
            const disabledComponents = getDisabledComponents();
            const isolatedComponents = viewerIsolatedComponent
                ? new Set([viewerIsolatedComponent])
                : (
                    viewerIsolatedNode
                        ? new Set(viewerIsolatedNode.components || [])
                        : null
                );
            const pickComponents = jointOriginPickMode && jointPickAllowedComponents
                ? jointPickAllowedComponents
                : null;
            Object.entries(meshDict).forEach(([component, mesh]) => {
                mesh.visible = visualMeshesEnabled
                    && !disabledComponents.has(component)
                    && (!isolatedComponents || isolatedComponents.has(component))
                    && (!pickComponents || pickComponents.has(component));
            });
            Object.entries(collisionMeshDict).forEach(([component, mesh]) => {
                mesh.visible = collisionMeshesEnabled
                    && !disabledComponents.has(component)
                    && (!isolatedComponents || isolatedComponents.has(component))
                    && (!pickComponents || pickComponents.has(component));
            });
        }

        function clearViewerIsolation(message = null) {
            if (!viewerIsolatedNode && !viewerIsolatedComponent) return false;
            viewerIsolatedNode = null;
            viewerIsolatedComponent = null;
            applyViewerIsolationVisibility();
            if (message) {
                const status = document.getElementById('viewer-pick-status');
                if (status) {
                    status.textContent = message;
                    status.style.display = 'block';
                }
            }
            return true;
        }

        function isolateSelectedJointChild() {
            if (!selectedElement || selectedElement.type !== 'joint' || !selectedElement.node) return;
            viewerIsolatedComponent = null;
            viewerIsolatedNode = selectedElement.node;
            applyViewerIsolationVisibility();
            const status = document.getElementById('viewer-pick-status');
            if (status) {
                status.textContent = `${selectedElement.node.name} 링크만 표시합니다. 내부 면을 선택한 뒤 전체 보기를 누르세요.`;
                status.style.display = 'block';
            }
        }

        function showAllViewerParts() {
            clearViewerIsolation('전체 링크 보기로 복원했습니다.');
        }

        function toggleVisualMeshes(visible) {
            visualMeshesEnabled = !!visible;
            applyViewerIsolationVisibility();
        }

        function toggleCollisionMeshes(visible) {
            collisionMeshesEnabled = !!visible;
            applyViewerIsolationVisibility();
        }

        function toggleInertiaMarkers(visible) {
            inertiaMarkers.forEach(marker => marker.visible = visible);
        }

        function toggleWorldFrame(visible) {
            if (worldFrameHelper) worldFrameHelper.visible = visible;
            if (gridHelper) gridHelper.visible = visible;
        }

        function updateSelectedJointFrameVisibility() {
            const showAllToggle = document.getElementById('show-joint-frames');
            const showAll = showAllToggle ? showAllToggle.checked : false;
            const selectedJoint = selectedElement?.type === 'joint'
                ? selectedElement.jointObj
                : null;
            jointFrameHelpers.forEach(helper => {
                const isSelected = !!selectedJoint && (
                    helper.userData.petasosJoint === selectedJoint
                    || helper.userData.petasosJointName === selectedJoint.joint_name
                );
                // A selected joint takes visual priority: hide every other
                // frame so the user can identify this joint unambiguously.
                helper.visible = selectedJoint ? isSelected : showAll;
            });
        }

        function toggleJointFrames(visible) {
            updateSelectedJointFrameVisibility();
        }

        function toggleLinkFrames(visible) {
            linkFrameHelpers.forEach(helper => helper.visible = visible);
        }

        function resizeJointFrames(size) {
            const scale = Number(size) / 120;
            jointFrameHelpers.forEach(helper => helper.scale.setScalar(scale));
        }

        function resizeLinkFrames(size) {
            const scale = Number(size) / 120;
            linkFrameHelpers.forEach(helper => helper.scale.setScalar(scale));
        }

        function findLinkByComponent(node, component) {
            if ((node.components || []).includes(component)) return node;
            for (const child of (node.children || [])) {
                const match = findLinkByComponent(child.link_group, component);
                if (match) return match;
            }
            return null;
        }

        function showViewerPickStatus(component, node, cleared = false) {
            const status = document.getElementById('viewer-pick-status');
            if (!status) return;
            status.innerText = cleared
                ? `${component} 집중 보기 해제 · 전체 부품 보기`
                : `${component} 부품만 집중 보기 · 다시 더블클릭하면 전체 보기`;
            status.style.display = 'block';
            clearTimeout(status._hideTimer);
            status._hideTimer = setTimeout(() => {
                status.style.display = 'none';
            }, 2200);
        }

        function updateSelectedLinkFinder() {
            const button = document.getElementById('tree-find-selected');
            if (!button) return;
            if (selectedElement && selectedElement.node) {
                button.style.display = 'block';
                button.innerText = `🎯 선택 링크 다시 찾기: ${selectedElement.node.name}`;
                button.title = `${selectedElement.node.name} 링크를 트리 중앙으로 이동`;
            } else {
                button.style.display = 'none';
            }
        }

        function findSelectedLinkInTree() {
            if (!selectedElement || !selectedElement.node) return;
            revealLinkInTree(selectedElement.node);
        }

        function revealLinkInTree(node) {
            requestAnimationFrame(() => {
                const treeBox = Array.from(
                    document.querySelectorAll('#tree .link-box')
                ).find(element => element._petasosNode === node);
                const pane = document.getElementById('viz-pane');
                if (!treeBox || !pane) return;

                const paneRect = pane.getBoundingClientRect();
                const boxRect = treeBox.getBoundingClientRect();
                pane.scrollTo({
                    left: pane.scrollLeft + boxRect.left - paneRect.left
                        - (pane.clientWidth - boxRect.width) / 2,
                    top: pane.scrollTop + boxRect.top - paneRect.top
                        - (pane.clientHeight - boxRect.height) / 2,
                    behavior: 'smooth'
                });
                treeBox.classList.add('viewer-located');
                setTimeout(() => treeBox.classList.remove('viewer-located'), 1800);
            });
        }

        function findMeshByProjectedBounds(clientX, clientY, rect) {
            const candidates = [];
            Object.entries(meshDict).forEach(([component, mesh]) => {
                if (!mesh.visible) return;
                if (!mesh.geometry.boundingBox) mesh.geometry.computeBoundingBox();
                const box = mesh.geometry.boundingBox;
                if (!box) return;
                const xs = [box.min.x, box.max.x];
                const ys = [box.min.y, box.max.y];
                const zs = [box.min.z, box.max.z];
                let minX = Infinity, maxX = -Infinity;
                let minY = Infinity, maxY = -Infinity;
                xs.forEach(x => ys.forEach(y => zs.forEach(z => {
                    const point = new THREE.Vector3(x, y, z);
                    mesh.localToWorld(point);
                    point.project(camera);
                    const screenX = rect.left + (point.x + 1) * rect.width / 2;
                    const screenY = rect.top + (1 - point.y) * rect.height / 2;
                    minX = Math.min(minX, screenX);
                    maxX = Math.max(maxX, screenX);
                    minY = Math.min(minY, screenY);
                    maxY = Math.max(maxY, screenY);
                })));
                const padding = 5;
                if (
                    clientX >= minX - padding && clientX <= maxX + padding
                    && clientY >= minY - padding && clientY <= maxY + padding
                ) {
                    const area = Math.max(1, (maxX - minX) * (maxY - minY));
                    const centerDistance = Math.hypot(
                        clientX - (minX + maxX) / 2,
                        clientY - (minY + maxY) / 2
                    );
                    candidates.push({ component, mesh, area, centerDistance });
                }
            });
            candidates.sort((a, b) => a.area - b.area || a.centerDistance - b.centerDistance);
            return candidates[0] || null;
        }

        function getViewerIntersections(event, options = {}) {
            if (!renderer || !camera) return [];
            const rect = renderer.domElement.getBoundingClientRect();
            viewerPointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
            viewerPointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
            if (options.refreshMatrices !== false) {
                scene.updateMatrixWorld(true);
                camera.updateMatrixWorld(true);
            }
            viewerRaycaster.setFromCamera(viewerPointer, camera);
            return viewerRaycaster.intersectObjects(
                Object.entries(meshDict)
                    .filter(([component, mesh]) => (
                        mesh.visible
                        && (
                            !jointOriginPickMode
                            || !jointPickAllowedComponents
                            || jointPickAllowedComponents.has(component)
                        )
                    ))
                    .map(([, mesh]) => mesh),
                false
            );
        }

        function screenDistanceToSegment(px, py, ax, ay, bx, by) {
            const dx = bx - ax;
            const dy = by - ay;
            const lengthSquared = dx * dx + dy * dy;
            if (lengthSquared <= 1e-9) return Math.hypot(px - ax, py - ay);
            const t = Math.max(0, Math.min(
                1,
                ((px - ax) * dx + (py - ay) * dy) / lengthSquared
            ));
            return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
        }

        function projectedCadSnapCandidates(event, intersections, options = {}) {
            if (!event || !renderer || !camera || !treeData) return [];
            const rect = renderer.domElement.getBoundingClientRect();
            const componentNames = new Set();
            const nearestSurfaceDepth = new Map();
            const intersectionPool = options.hoverOnly
                ? (intersections || []).slice(0, 12)
                : (intersections || []);
            intersectionPool.forEach(hit => {
                const component = hit && viewerComponentForObject(hit.object);
                if (!component) return;
                componentNames.add(component);
                const distance = Number(hit.distance);
                if (
                    Number.isFinite(distance)
                    && (
                        !nearestSurfaceDepth.has(component)
                        || distance < nearestSurfaceDepth.get(component)
                    )
                ) {
                    nearestSurfaceDepth.set(component, distance);
                }
            });
            if (
                options.includeHiddenDepthCandidates
                && !options.hoverOnly
                && selectedElement
                && selectedElement.node
            ) {
                (selectedElement.node.components || []).forEach(component => {
                    if (
                        meshDict[component]
                        && meshDict[component].visible
                        && (
                            !jointOriginPickMode
                            || !jointPickAllowedComponents
                            || jointPickAllowedComponents.has(component)
                        )
                    ) {
                        componentNames.add(component);
                    }
                });
            }
            const priority = {
                circle_center: 0,
                arc_center: 0,
                cylinder_axis: 1,
                planar_face_center: 2,
                edge_midpoint: 3,
                vertex: 4,
            };
            const candidates = [];

            componentNames.forEach(component => {
                const mesh = meshDict[component];
                const record = (treeData._cad_snap_features || {})[component];
                const features = record && Array.isArray(record.features)
                    ? record.features
                    : [];
                if (!mesh || !features.length) return;
                if (!mesh.geometry.boundingBox) mesh.geometry.computeBoundingBox();
                const geometrySize = new THREE.Vector3();
                mesh.geometry.boundingBox.getSize(geometrySize);
                const diagonal = Math.max(geometrySize.length(), 1);

                features.forEach(feature => {
                    const type = String(feature && feature.type || '');
                    if (!(type in priority) || !Array.isArray(feature.position)) return;
                    const localCenter = new THREE.Vector3().fromArray(feature.position);
                    const radius = Number(feature.radius || 0);
                    const maximumCadExtent = diagonal * 8;
                    const featureCenterDistance = mesh.geometry.boundingBox
                        .distanceToPoint(localCenter);
                    if (
                        featureCenterDistance > maximumCadExtent
                        || (
                            ['circle_center', 'arc_center', 'cylinder_axis'].includes(type)
                            && radius > maximumCadExtent
                        )
                    ) return;
                    const worldCenter = mesh.localToWorld(localCenter.clone());
                    const projectedCenter = worldCenter.clone().project(camera);
                    if (projectedCenter.z < -1 || projectedCenter.z > 1) return;
                    const centerX = rect.left + (projectedCenter.x + 1) * rect.width / 2;
                    const centerY = rect.top + (1 - projectedCenter.y) * rect.height / 2;
                    const centerDistance = Math.hypot(
                        event.clientX - centerX,
                        event.clientY - centerY
                    );
                    let screenScore = centerDistance / (
                        type === 'edge_midpoint' || type === 'vertex' ? 13 : 19
                    );
                    let matchedBy = 'center';

                    const candidateDepth = camera.position.distanceTo(worldCenter);
                    const visibleSurfaceDepth = nearestSurfaceDepth.get(component);
                    const depthTolerance = Math.max(
                        diagonal * 0.015,
                        radius > 0 ? radius * 0.04 : 0,
                        0.5
                    );
                    if (
                        Number.isFinite(visibleSurfaceDepth)
                        && candidateDepth > visibleSurfaceDepth + depthTolerance
                    ) {
                        return;
                    }
                    const localNormal = Array.isArray(feature.normal)
                        ? new THREE.Vector3().fromArray(feature.normal).normalize()
                        : null;
                    const localTangent = Array.isArray(feature.tangent)
                        ? new THREE.Vector3().fromArray(feature.tangent).normalize()
                        : null;
                    if (
                        radius > 0
                        && localNormal && localNormal.lengthSq() > 0.9
                        && localTangent && localTangent.lengthSq() > 0.9
                        && ['circle_center', 'arc_center', 'cylinder_axis'].includes(type)
                    ) {
                        const secondAxis = new THREE.Vector3()
                            .crossVectors(localNormal, localTangent)
                            .normalize();
                        let ringDistance = Infinity;
                        if (options.hoverOnly) {
                            // Two projected radius vectors are enough to estimate
                            // the screen ellipse during hover. The full rim is
                            // evaluated only on click.
                            const tangentPoint = mesh.localToWorld(
                                localCenter.clone().addScaledVector(
                                    localTangent,
                                    radius
                                )
                            ).project(camera);
                            const secondPoint = mesh.localToWorld(
                                localCenter.clone().addScaledVector(
                                    secondAxis,
                                    radius
                                )
                            ).project(camera);
                            const ux = (
                                rect.left + (tangentPoint.x + 1) * rect.width / 2
                            ) - centerX;
                            const uy = (
                                rect.top + (1 - tangentPoint.y) * rect.height / 2
                            ) - centerY;
                            const vx = (
                                rect.left + (secondPoint.x + 1) * rect.width / 2
                            ) - centerX;
                            const vy = (
                                rect.top + (1 - secondPoint.y) * rect.height / 2
                            ) - centerY;
                            const dx = event.clientX - centerX;
                            const dy = event.clientY - centerY;
                            const determinant = ux * vy - uy * vx;
                            if (Math.abs(determinant) > 1e-6) {
                                const uAmount = (dx * vy - dy * vx) / determinant;
                                const vAmount = (ux * dy - uy * dx) / determinant;
                                const normalizedRadius = Math.hypot(
                                    uAmount,
                                    vAmount
                                );
                                const screenRadius = Math.max(
                                    1,
                                    Math.min(Math.hypot(ux, uy), Math.hypot(vx, vy))
                                );
                                ringDistance = Math.abs(normalizedRadius - 1)
                                    * screenRadius;
                            }
                        } else {
                            const ringPoints = [];
                            const ringSegments = 24;
                            for (let index = 0; index <= ringSegments; index += 1) {
                                const angle = index / ringSegments * Math.PI * 2;
                                const localPoint = localCenter.clone()
                                    .addScaledVector(localTangent, Math.cos(angle) * radius)
                                    .addScaledVector(secondAxis, Math.sin(angle) * radius);
                                const projected = mesh.localToWorld(localPoint).project(camera);
                                ringPoints.push({
                                    x: rect.left + (projected.x + 1) * rect.width / 2,
                                    y: rect.top + (1 - projected.y) * rect.height / 2,
                                });
                            }
                            for (let index = 1; index < ringPoints.length; index += 1) {
                                ringDistance = Math.min(
                                    ringDistance,
                                    screenDistanceToSegment(
                                        event.clientX,
                                        event.clientY,
                                        ringPoints[index - 1].x,
                                        ringPoints[index - 1].y,
                                        ringPoints[index].x,
                                        ringPoints[index].y
                                    )
                                );
                            }
                        }
                        const ringScore = 0.25 + ringDistance / 13;
                        if (ringScore < screenScore) {
                            screenScore = ringScore;
                            matchedBy = 'rim';
                        }
                    }
                    if (!Number.isFinite(screenScore) || screenScore > 1.25) return;

                    const normal = localNormal || (
                        intersections.find(hit => viewerComponentForObject(hit.object) === component)
                            ?.face?.normal?.clone()?.normalize()
                    ) || new THREE.Vector3(0, 0, 1);
                    const snapMode = `cad_${type}`;
                    const snap = {
                        localCenter,
                        localNormal: normal,
                        localTangent,
                        snapMode,
                        snapSource: 'opencascade',
                        cadFeatureType: type,
                        cadEntityId: feature.entity_id || null,
                        circleRadius: radius || null,
                        snapMatchScore: priority[type] * 10 + screenScore,
                        minimumNormalAgreement: 1,
                        triangleCount: 0,
                        patchDiagonal: diagonal,
                        boundaryDirectionClusters: 0,
                        area: Number(feature.area || 0),
                        matchedBy,
                    };
                    candidates.push({
                        hit: {
                            object: mesh,
                            point: worldCenter,
                            distance: candidateDepth,
                            face: { normal: normal.clone() },
                        },
                        snap,
                        component,
                        score: snap.snapMatchScore,
                        depth: candidateDepth,
                    });
                });
            });
            return candidates;
        }

        function resolveBestSurfaceSnap(intersections, event = null, options = {}) {
            if ((groundFacePickMode || baseFootprintPickMode) && !jointOriginPickMode) {
                const groundHit = (intersections || []).find(
                    item => item && item.face && item.object
                );
                if (groundHit) {
                    const groundSnap = resolveSurfaceSnap(
                        groundHit,
                        planarFaceSnapCandidate(groundHit),
                        true
                    );
                    if (groundSnap) {
                        return {
                            hit: groundHit,
                            snap: groundSnap,
                            component: viewerComponentForObject(groundHit.object) || '',
                            candidateIndex: 0,
                            candidateCount: 1,
                            usedDepthSelection: false,
                        };
                    }
                }
            }
            const exactCandidates = projectedCadSnapCandidates(
                event,
                intersections,
                options
            );
            const seenCadEntities = new Set();
            exactCandidates.forEach(candidate => {
                const centerKey = candidate.snap.localCenter.toArray()
                    .map(value => Number(value).toFixed(5))
                    .join(',');
                seenCadEntities.add([
                    candidate.component,
                    candidate.snap.cadEntityId || candidate.snap.snapMode,
                    centerKey,
                ].join('|'));
            });
            if (!options.hoverOnly) {
                (intersections || [])
                    .filter(item => item && item.face && item.object)
                    .slice(0, 96)
                    .forEach(hit => {
                    const snap = cadSnapCandidate(hit, null);
                    if (!snap) return;
                    const component = viewerComponentForObject(hit.object) || '';
                    const centerKey = snap.localCenter.toArray()
                        .map(value => Number(value).toFixed(5))
                        .join(',');
                    const entityKey = [
                        component,
                        snap.cadEntityId || snap.snapMode,
                        centerKey,
                    ].join('|');
                    if (seenCadEntities.has(entityKey)) return;
                    seenCadEntities.add(entityKey);
                    exactCandidates.push({
                        hit,
                        snap,
                        component,
                        score: Number(snap.snapMatchScore || 0),
                        depth: Number(hit.distance || 0),
                    });
                });
            }
            exactCandidates.sort(
                (a, b) => a.score - b.score || a.depth - b.depth
            );
            const uniqueCandidateKeys = new Set();
            const rankedCandidates = exactCandidates.filter(candidate => {
                const key = jointSnapCandidateKey(candidate);
                if (!key || uniqueCandidateKeys.has(key)) return false;
                uniqueCandidateKeys.add(key);
                return true;
            });
            const selectableCandidates = jointOriginPickMode
                ? rankedCandidates.slice(0, 24)
                : rankedCandidates;
            if (selectableCandidates.length > 0) {
                jointSnapCandidateCache = jointOriginPickMode
                    ? selectableCandidates.slice()
                    : jointSnapCandidateCache;
                let candidateIndex = jointOriginPickMode && jointSnapSelectedKey
                    ? selectableCandidates.findIndex(
                        candidate => jointSnapCandidateKey(candidate) === jointSnapSelectedKey
                    )
                    : 0;
                if (candidateIndex < 0) {
                    candidateIndex = 0;
                    if (jointOriginPickMode) {
                        jointSnapSelectedKey = jointSnapCandidateKey(selectableCandidates[0]);
                    }
                }
                if (jointOriginPickMode && !jointSnapSelectedKey) {
                    jointSnapSelectedKey = jointSnapCandidateKey(
                        selectableCandidates[candidateIndex]
                    );
                }
                if (event && event.shiftKey && selectableCandidates.length > 1) {
                    candidateIndex = (
                        candidateIndex + 1
                    ) % selectableCandidates.length;
                }
                return {
                    ...selectableCandidates[candidateIndex],
                    candidateIndex,
                    candidateCount: selectableCandidates.length,
                    rawCandidateCount: exactCandidates.length,
                    uniqueCandidateCount: rankedCandidates.length,
                    usedDepthSelection: candidateIndex > 0,
                };
            }

            // Connected planar-region fitting scans every triangle in the STL.
            // Keep hover responsive and reserve that exact fallback for a click.
            if (options.hoverOnly) return null;
            const hit = (intersections || []).find(item => item.face && item.object);
            if (!hit) return null;
            const snap = resolveSurfaceSnap(hit, planarFaceSnapCandidate(hit));
            if (!snap) return null;
            if (jointOriginPickMode) jointSnapCandidateCache = [];
            return {
                hit,
                snap,
                component: viewerComponentForObject(hit.object) || '',
                candidateIndex: 0,
                candidateCount: 1,
                usedDepthSelection: false,
            };
        }

        function handleBaseFootprintPick(event) {
            if (!robotRoot || !treeData || !baseFootprintPickMode) return;
            const intersections = getViewerIntersections(event);
            const selection = resolveBestSurfaceSnap(intersections, event);
            if (!selection) {
                updateBaseFootprintPickUi('BASE FOOTPRINT 위치를 찾지 못했습니다. 평평한 면을 다시 클릭하세요.');
                return;
            }
            const { hit, snap } = selection;
            const component = selection.component || '선택한 부품';
            const worldPoint = hit.object.localToWorld(snap.localCenter.clone());
            const rosFrame = new THREE.Quaternion().setFromEuler(
                new THREE.Euler(Math.PI / 2, 0, 0, 'XYZ')
            );
            const unitsPerMeter = Number(treeData._preview_units_per_meter) || 1000.0;
            const rosWorldPoint = worldPoint.clone()
                .applyQuaternion(rosFrame)
                .divideScalar(unitsPerMeter);
            saveState();
            treeData._base_footprint_frame = {
                component,
                snap_mode: snap.snapMode || 'connected_planar_face_centroid',
                center_local: snap.localCenter.toArray(),
                world_xyz: rosWorldPoint.toArray(),
                rpy: Array.isArray(treeData._base_footprint_frame?.rpy)
                    ? treeData._base_footprint_frame.rpy.slice(0, 3)
                    : [0, 0, Number(treeData._base_footprint_frame?.yaw || 0)],
                yaw: Number(treeData._base_footprint_frame?.yaw || 0),
            };
            baseFootprintPickMode = false;
            hideGroundSnapMarker();
            showBaseFootprintFrameMarker();
            render({ skipPreview: true });
            updateGroundFaceUi();
            updateBaseFootprintPickUi(
                `BASE FOOTPRINT 위치 지정 완료: ${component} · ROS XYZ ${rosWorldPoint.toArray().map(value => (value * 1000).toFixed(1)).join(', ')} mm`
            );
        }

        function handleGroundFacePick(event) {
            if (!robotRoot || !treeData) return;
            const intersections = getViewerIntersections(event);
            const selection = resolveBestSurfaceSnap(intersections, event);
            if (!selection) {
                updateGroundFaceUi('면을 찾지 못했습니다. 모델의 평평한 면을 다시 클릭하세요.');
                return;
            }
            const { hit, snap } = selection;
            const component = selection.component || '선택한 부품';
            const faceCenterWorld = hit.object.localToWorld(snap.localCenter.clone());
            const rootLocalCenter = robotRoot.worldToLocal(faceCenterWorld.clone());
            const boxBefore = new THREE.Box3();
            Object.values(meshDict).forEach(mesh => boxBefore.expandByObject(mesh));
            const modelCenter = new THREE.Vector3();
            boxBefore.getCenter(modelCenter);

            const towardModel = modelCenter.sub(hit.point).normalize();
            const supportDirection = snap.localNormal.clone()
                .transformDirection(hit.object.matrixWorld)
                .normalize();
            if (supportDirection.dot(towardModel) < 0) supportDirection.negate();
            if (!Number.isFinite(supportDirection.x) || supportDirection.lengthSq() < 0.5) {
                updateGroundFaceUi('이 면의 방향을 계산하지 못했습니다. 다른 평평한 면을 선택하세요.');
                return;
            }

            saveState();
            const alignToUp = new THREE.Quaternion().setFromUnitVectors(
                supportDirection,
                new THREE.Vector3(0, 1, 0)
            );
            const edgeAlignEnabled = !!document.getElementById('ground-align-edge')?.checked;
            let yawAlignment = null;
            let targetAxisName = null;
            if (edgeAlignEnabled && snap.localTangent) {
                const tangentWorld = snap.localTangent.clone()
                    .transformDirection(hit.object.matrixWorld)
                    .normalize()
                    .applyQuaternion(alignToUp);
                tangentWorld.y = 0;
                if (tangentWorld.lengthSq() > 0.5) {
                    tangentWorld.normalize();
                    const axisTargets = [
                        { name: '+X', vector: new THREE.Vector3(1, 0, 0) },
                        { name: '-X', vector: new THREE.Vector3(-1, 0, 0) },
                        { name: '+Z', vector: new THREE.Vector3(0, 0, 1) },
                        { name: '-Z', vector: new THREE.Vector3(0, 0, -1) },
                    ];
                    axisTargets.sort(
                        (a, b) => b.vector.dot(tangentWorld) - a.vector.dot(tangentWorld)
                    );
                    const targetAxis = axisTargets[0];
                    const cross = new THREE.Vector3().crossVectors(
                        tangentWorld,
                        targetAxis.vector
                    );
                    const yawAngle = Math.atan2(
                        cross.dot(new THREE.Vector3(0, 1, 0)),
                        tangentWorld.dot(targetAxis.vector)
                    );
                    yawAlignment = new THREE.Quaternion().setFromAxisAngle(
                        new THREE.Vector3(0, 1, 0),
                        yawAngle
                    );
                    targetAxisName = targetAxis.name;
                }
            }
            robotRoot.position.set(0, 0, 0);
            robotRoot.quaternion.premultiply(alignToUp).normalize();
            if (yawAlignment) robotRoot.quaternion.premultiply(yawAlignment).normalize();
            robotRoot.updateMatrixWorld(true);
            const alignedCenterWorld = robotRoot.localToWorld(rootLocalCenter.clone());
            robotRoot.position.sub(alignedCenterWorld);
            robotRoot.updateMatrixWorld(true);

            // A mesh triangle winding can report the opposite face normal.
            // Keep the selected point at the origin, but ensure the robot bulk
            // lies above the ground plane instead of below it.
            const alignedBounds = new THREE.Box3();
            Object.values(meshDict).forEach(mesh => alignedBounds.expandByObject(mesh));
            const alignedSize = new THREE.Vector3();
            const alignedModelCenter = new THREE.Vector3();
            alignedBounds.getSize(alignedSize);
            alignedBounds.getCenter(alignedModelCenter);
            const verticalTolerance = Math.max(alignedSize.y * 0.0001, 0.0001);
            let normalFlippedToKeepModelAbove = false;
            if (alignedModelCenter.y < -verticalTolerance) {
                const flipAroundWorldX = new THREE.Quaternion().setFromAxisAngle(
                    new THREE.Vector3(1, 0, 0),
                    Math.PI
                );
                robotRoot.quaternion.premultiply(flipAroundWorldX).normalize();
                robotRoot.updateMatrixWorld(true);
                const flippedAnchorWorld = robotRoot.localToWorld(rootLocalCenter.clone());
                robotRoot.position.sub(flippedAnchorWorld);
                robotRoot.updateMatrixWorld(true);
                normalFlippedToKeepModelAbove = true;
            }

            treeData._preview_ground_face = {
                component,
                snap_mode: snap.snapMode || 'connected_planar_face_centroid',
                snap_source: snap.snapSource || 'mesh_inference',
                cad_feature_type: snap.cadFeatureType || null,
                cad_entity_id: snap.cadEntityId || null,
                matched_by: snap.matchedBy || null,
                candidate_count: selection.candidateCount,
                candidate_index: selection.candidateIndex,
                depth_selected: selection.usedDepthSelection,
                circle_radius: snap.circleRadius || null,
                center_local: snap.localCenter.toArray(),
                tangent_local: snap.localTangent ? snap.localTangent.toArray() : null,
                triangle_count: snap.triangleCount,
                alignment_mode: yawAlignment
                    ? 'normal_center_and_boundary_axis'
                    : 'normal_and_center',
                target_axis: targetAxisName,
                normal_flipped_to_keep_model_above: normalFlippedToKeepModelAbove,
                world_origin: [0, 0, 0],
                origin_offset_xyz: [0, 0, 0],
            };
            syncPreviewRootTransform();
            groundFacePickMode = false;
            showGroundSnapMarker(
                new THREE.Vector3(0, 0, 0),
                new THREE.Vector3(0, 1, 0),
                true
            );
            fitCameraToRobot();
            refreshWorldReferencePlane(0);
            const centerText = snap.localCenter.toArray()
                .map(value => Number(value).toFixed(2))
                .join(', ');
            const axisText = targetAxisName
                ? ` · 긴 모서리 → 월드 ${targetAxisName}`
                : ' · 평면 내 회전 유지';
            const snapLabel = snapDisplayLabel(snap);
            render({ skipPreview: true });
            updateGroundFaceUi(
                `원점 지정 완료: ${component} ${snapLabel} [${centerText}] → 월드 XYZ 0,0,0${axisText}`
            );
        }

        function jointEntryFor(joint) {
            if (!treeData || !joint) return null;
            return getFlatLinks(treeData, null, -1).find(item => item.jointObj === joint) || null;
        }

        function previewFrameMatrixForNode(node) {
            if (node && node !== treeData) {
                const entry = jointEntryForNode(node);
                const jointInfo = entry && entry.jointObj && entry.jointObj.joint_info;
                const pickedFrame = jointInfo && jointInfo._preview_world_frame_matrix;
                if (Array.isArray(pickedFrame) && pickedFrame.length === 16) {
                    return new THREE.Matrix4().fromArray(pickedFrame);
                }
            }
            const component = (node && node.components || [])[0];
            const values = component && treeData && treeData._preview_transforms
                ? treeData._preview_transforms[component]
                : null;
            if (Array.isArray(values) && values.length === 16) {
                return new THREE.Matrix4().fromArray(values);
            }
            return new THREE.Matrix4();
        }

        function jointEntryForNode(node) {
            if (!treeData || !node) return null;
            return getFlatLinks(treeData, null, -1).find(item => item.node === node) || null;
        }

        function syncPickedJointLocalFrames() {
            if (!treeData) return;
            const unitsPerMeter = Number(treeData._preview_units_per_meter) || 1000.0;
            const rootFrame = (() => {
                const component = (treeData.components || [])[0];
                const values = component && treeData._preview_transforms
                    ? treeData._preview_transforms[component]
                    : null;
                return Array.isArray(values) && values.length === 16
                    ? new THREE.Matrix4().fromArray(values)
                    : new THREE.Matrix4();
            })();

            const walk = (node, parentFrame) => {
                (node.children || []).forEach(child => {
                    const jointInfo = child.joint_info || {};
                    child.joint_info = jointInfo;
                    const pickedFrame = jointInfo._preview_world_frame_matrix;
                    let childFrame;
                    if (Array.isArray(pickedFrame) && pickedFrame.length === 16) {
                        childFrame = new THREE.Matrix4().fromArray(pickedFrame);
                        const localFrame = parentFrame.clone().invert().multiply(childFrame);
                        const position = new THREE.Vector3();
                        const quaternion = new THREE.Quaternion();
                        const scale = new THREE.Vector3();
                        localFrame.decompose(position, quaternion, scale);
                        const euler = new THREE.Euler().setFromQuaternion(quaternion, 'ZYX');
                        jointInfo.xyz = position.divideScalar(unitsPerMeter).toArray();
                        jointInfo.rpy = [euler.x, euler.y, euler.z];
                        jointInfo._manual_rpy = jointInfo.rpy.slice();
                        jointInfo._preview_local_quaternion = quaternion.toArray();
                    } else {
                        const xyz = jointInfo.xyz || [0, 0, 0];
                        const rpy = jointInfo._manual_rpy || jointInfo.rpy || [0, 0, 0];
                        const localFrame = new THREE.Matrix4().compose(
                            new THREE.Vector3(
                                xyz[0] * unitsPerMeter,
                                xyz[1] * unitsPerMeter,
                                xyz[2] * unitsPerMeter
                            ),
                            new THREE.Quaternion().setFromEuler(
                                new THREE.Euler(rpy[0], rpy[1], rpy[2], 'ZYX')
                            ),
                            new THREE.Vector3(1, 1, 1)
                        );
                        childFrame = parentFrame.clone().multiply(localFrame);
                    }
                    walk(child.link_group, childFrame);
                });
            };
            walk(treeData, rootFrame);
        }

        function jointFrameFromSurface(
            rootPoint,
            rootNormal,
            rootTangent = null,
            preferredXAxis = null
        ) {
            const zAxis = rootNormal.clone().normalize();
            let xAxis = rootTangent
                ? rootTangent.clone()
                : (preferredXAxis ? preferredXAxis.clone() : new THREE.Vector3());
            xAxis.addScaledVector(zAxis, -xAxis.dot(zAxis));
            if (xAxis.lengthSq() < 1e-8) {
                const fallbackAxes = [
                    new THREE.Vector3(1, 0, 0),
                    new THREE.Vector3(0, 1, 0),
                    new THREE.Vector3(0, 0, 1),
                ].sort((a, b) => Math.abs(a.dot(zAxis)) - Math.abs(b.dot(zAxis)));
                xAxis.copy(fallbackAxes[0]).addScaledVector(
                    zAxis,
                    -fallbackAxes[0].dot(zAxis)
                );
            }
            xAxis.normalize();
            const yAxis = new THREE.Vector3().crossVectors(zAxis, xAxis).normalize();
            xAxis.crossVectors(yAxis, zAxis).normalize();
            yAxis.crossVectors(zAxis, xAxis).normalize();
            const orthogonalityError = Math.max(
                Math.abs(xAxis.dot(yAxis)),
                Math.abs(xAxis.dot(zAxis)),
                Math.abs(yAxis.dot(zAxis)),
                Math.abs(xAxis.length() - 1),
                Math.abs(yAxis.length() - 1),
                Math.abs(zAxis.length() - 1)
            );
            return {
                matrix: new THREE.Matrix4().makeBasis(xAxis, yAxis, zAxis).setPosition(rootPoint),
                xAxis,
                yAxis,
                zAxis,
                orthogonalityError,
            };
        }

        function jointPickScopeNode() {
            const entry = jointEntryFor(jointOriginPickJoint);
            if (!entry) return selectedElement && selectedElement.node;
            return jointOriginPickStage === 'parent'
                ? entry.parentNode
                : entry.node;
        }

        function jointPickScopeComponents() {
            const node = jointPickScopeNode();
            return node && Array.isArray(node.components)
                ? node.components
                : [];
        }

        function updateJointOriginPickUi(message) {
            const button = document.getElementById('joint-origin-pick-button');
            const help = document.getElementById('joint-origin-pick-help');
            const tools = document.getElementById('joint-origin-pick-tools');
            const componentSelect = document.getElementById('joint-pick-component-select');
            const scopeSummary = document.getElementById('joint-pick-scope-summary');
            const container = document.getElementById('viewer-3d-container');
            if (button) {
                button.classList.toggle('active', jointOriginPickMode);
                button.textContent = jointOriginPickMode
                    ? '✕ 조인트 위치 지정 취소'
                    : '🎯 3D에서 조인트 중심·축 다시 찍기';
            }
            if (help && message) help.textContent = message;
            if (tools) tools.style.display = jointOriginPickMode ? 'block' : 'none';
            if (componentSelect) {
                const components = jointPickScopeComponents();
                const scopeKey = [
                    jointOriginPickStage,
                    ...components,
                ].join('|');
                if (componentSelect.dataset.scopeKey !== scopeKey) {
                    componentSelect.dataset.scopeKey = scopeKey;
                    componentSelect.innerHTML = [
                        `<option value="-1">${
                            jointOriginPickStage === 'parent' ? '부모' : '자식'
                        } 링크 전체 (${components.length}개 부품)</option>`,
                        ...components.map((component, index) => (
                            `<option value="${index}">${component}</option>`
                        )),
                    ].join('');
                }
                const selectedIndex = jointPickTargetComponent
                    ? components.indexOf(jointPickTargetComponent)
                    : -1;
                componentSelect.value = String(selectedIndex);
            }
            if (scopeSummary && jointOriginPickMode) {
                const allowedCount = jointPickAllowedComponents
                    ? jointPickAllowedComponents.size
                    : 0;
                scopeSummary.textContent = jointPickTargetComponent
                    ? `이 부품만 화면과 클릭 판정에 남김: ${jointPickTargetComponent}`
                    : `자식 링크의 ${allowedCount}개 부품만 화면과 클릭 판정에 남김`;
                const stageLabel = jointOriginPickStage === 'parent'
                    ? '1/2 부모 연결점'
                    : '2/2 자식 연결점';
                scopeSummary.textContent = jointPickTargetComponent
                    ? `${stageLabel} · 이 부품만 판정: ${jointPickTargetComponent}`
                    : `${stageLabel} · ${allowedCount}개 부품에서 판정`;
            }
            if (container) container.classList.toggle('joint-origin-picking', jointOriginPickMode);
            if (message) {
                const viewerStatus = document.getElementById('viewer-pick-status');
                if (viewerStatus) {
                    viewerStatus.textContent = message;
                    viewerStatus.style.display = 'block';
                }
            }
        }

        function jointSnapCandidateKey(candidate) {
            if (!candidate || !candidate.snap) return '';
            const center = candidate.snap.localCenter
                ? candidate.snap.localCenter.toArray()
                    .map(value => Number(value).toFixed(3)).join(',')
                : '';
            const normal = candidate.snap.localNormal
                ? candidate.snap.localNormal.toArray()
                    .map(value => Number(value).toFixed(3)).join(',')
                : '';
            return [
                candidate.component || '',
                candidate.snap.snapMode || '',
                center,
                normal,
            ].join('|');
        }

        function clearJointSnapCandidateState() {
            jointSnapCandidateCache = [];
            jointSnapSelectedKey = null;
            jointSnapControlsSignature = '';
            updateJointSnapCandidateControls(null);
        }

        function updateJointSnapCandidateControls(selection = null) {
            const select = document.getElementById('joint-snap-candidate-select');
            const summary = document.getElementById('joint-snap-candidate-summary');
            if (!select || !summary) return;
            const signature = [
                jointSnapCandidateCache
                    .map(candidate => jointSnapCandidateKey(candidate))
                    .join('||'),
                selection && Number.isInteger(Number(selection.candidateIndex))
                    ? Number(selection.candidateIndex)
                    : jointSnapSelectedKey || '',
            ].join('::');
            if (signature === jointSnapControlsSignature) return;
            jointSnapControlsSignature = signature;
            select.innerHTML = '';
            if (!jointSnapCandidateCache.length) {
                const option = document.createElement('option');
                option.value = '-1';
                option.textContent = '정밀 CAD 후보 없음 — 메쉬 추정 사용';
                select.appendChild(option);
                select.disabled = true;
                summary.textContent = '이 프로젝트는 IAM을 다시 가져와야 원·호 중심을 정밀하게 잡을 수 있습니다.';
                return;
            }
            select.disabled = false;
            let selectedIndex = Number(selection && selection.candidateIndex);
            if (!Number.isInteger(selectedIndex) || selectedIndex < 0) {
                selectedIndex = jointSnapCandidateCache.findIndex(
                    candidate => jointSnapCandidateKey(candidate) === jointSnapSelectedKey
                );
            }
            if (selectedIndex < 0) selectedIndex = 0;
            jointSnapCandidateCache.forEach((candidate, index) => {
                const option = document.createElement('option');
                const radius = Number(candidate.snap.circleRadius || 0);
                option.value = String(index);
                option.textContent = `${index + 1}. ${snapDisplayLabel(candidate.snap)} · ${
                    candidate.component || '부품'
                }${radius > 0 ? ` · R ${radius.toFixed(2)}` : ''}`;
                select.appendChild(option);
            });
            select.value = String(selectedIndex);
            summary.textContent = jointSnapCandidateCache.length > 1
                ? `겹친 자석 ${jointSnapCandidateCache.length}개 — 목록에서 안쪽 원·호를 직접 고르세요.`
                : '정밀 CAD 자석에 붙었습니다.';
        }

        function selectJointSnapCandidate(value) {
            const index = Number(value);
            const candidate = jointSnapCandidateCache[index];
            if (!candidate) return;
            jointSnapSelectedKey = jointSnapCandidateKey(candidate);
            if (groundSnapHoverEvent) updateGroundFaceSnapPreview(groundSnapHoverEvent);
        }

        function cycleJointSnapCandidate(delta) {
            if (!jointSnapCandidateCache.length) return;
            let index = jointSnapCandidateCache.findIndex(
                candidate => jointSnapCandidateKey(candidate) === jointSnapSelectedKey
            );
            if (index < 0) index = 0;
            index = (
                index + Number(delta || 0) + jointSnapCandidateCache.length
            ) % jointSnapCandidateCache.length;
            selectJointSnapCandidate(index);
        }

        function setJointPickComponentScope(value) {
            if (!jointOriginPickMode || !selectedElement || !selectedElement.node) return;
            const components = jointPickScopeComponents();
            const index = Number(value);
            jointPickTargetComponent = Number.isInteger(index) && index >= 0
                ? components[index] || null
                : null;
            jointPickAllowedComponents = new Set(
                jointPickTargetComponent ? [jointPickTargetComponent] : components
            );
            clearJointSnapCandidateState();
            hideJointSnapMarker();
            refreshJointPickStageViewer();
            updateJointOriginPickUi(
                jointPickTargetComponent
                    ? `${jointPickTargetComponent} 부품만 남겼습니다. 원하는 원·호로 마우스를 옮기세요.`
                    : `자식 링크의 ${components.length}개 부품만 남겼습니다. 겹친 후보는 아래 목록에서 고르세요.`
            );
        }

        function refreshJointPickStageViewer() {
            applyViewerIsolationVisibility();
            if (!jointOriginPickMode) {
                refreshViewerColors();
                return;
            }
            // Joint picking owns the viewer temporarily. Restore the active
            // parent/child link's real group colors instead of leaving the
            // previous child selection as a nearly invisible ghost.
            applyLinkGroupColors();
            (jointPickAllowedComponents || []).forEach(component => {
                const edge = meshEdgeDict[component];
                if (edge) {
                    edge.visible = true;
                    edge.material.opacity = 0.72;
                }
            });
        }

        function endJointOriginPickScope() {
            jointPickAllowedComponents = null;
            jointPickTargetComponent = null;
            jointOriginPickStage = 'parent';
            jointOriginParentSnap = null;
            clearJointSnapCandidateState();
            applyViewerIsolationVisibility();
            refreshViewerColors();
        }

        function cancelJointOriginPick(message = '조인트 위치 지정을 취소했습니다.') {
            jointOriginPickMode = false;
            jointOriginPickJoint = null;
            hideJointSnapMarker();
            endJointOriginPickScope();
            updateJointOriginPickUi(message);
        }

        function toggleJointOriginPick() {
            if (!selectedElement || selectedElement.type !== 'joint' || !selectedElement.jointObj) return;
            if (jointOriginPickMode && jointOriginPickJoint === selectedElement.jointObj) {
                cancelJointOriginPick();
                return;
            }
            groundFacePickMode = false;
            baseFootprintPickMode = false;
            updateGroundFaceUi('바닥면 지정 대기');
            activeJointSnapMarkerInfo = null;
            hideGroundSnapMarker();
            hideJointSnapMarker();
            // Joint mates must be picked from the imported assembly pose,
            // never from a temporary slider preview pose.
            restoreImportedAssemblyPose(false);
            jointOriginPickMode = true;
            jointOriginPickJoint = selectedElement.jointObj;
            jointOriginPickStage = 'parent';
            jointOriginParentSnap = null;
            jointPickTargetComponent = null;
            viewerIsolatedNode = null;
            viewerIsolatedComponent = null;
            const entry = jointEntryFor(jointOriginPickJoint);
            const parentComponents = entry && entry.parentNode
                ? entry.parentNode.components || []
                : [];
            jointPickAllowedComponents = new Set(parentComponents);
            clearJointSnapCandidateState();
            refreshJointPickStageViewer();
            const exactFeatureCount = Array.from(jointPickAllowedComponents)
                .reduce((total, component) => {
                    const record = (treeData._cad_snap_features || {})[component];
                    return total + (
                        record && Array.isArray(record.features)
                            ? record.features.length
                            : 0
                    );
                }, 0);
            updateJointOriginPickUi(
                exactFeatureCount > 0
                    ? `자식 링크 밖의 부품을 완전히 제외했습니다. 정밀 CAD 자석 ${exactFeatureCount}개 중 원하는 원·호를 고르세요.`
                    : '자식 링크 밖의 부품을 완전히 제외했습니다. 단, 이 프로젝트에는 정밀 CAD 자석이 없으므로 IAM을 다시 가져와야 원·호 중심이 정확해집니다.'
            );
            updateJointOriginPickUi(
                `1/2 부모 연결점: 부모 링크의 원·호 중심 또는 평면 중심을 선택하세요.`
            );
        }

        function handleJointOriginPick(event) {
            const joint = jointOriginPickJoint;
            const entry = jointEntryFor(joint);
            if (!joint || !entry || !entry.parentNode || !robotRoot || !treeData) {
                cancelJointOriginPick('선택한 조인트의 부모 링크를 찾지 못했습니다.');
                return;
            }
            const intersections = getViewerIntersections(event);
            const selection = resolveBestSurfaceSnap(intersections, event);
            if (!selection) {
                updateJointOriginPickUi('CAD 스냅 또는 평면 중심을 찾지 못했습니다. 원·호 테두리나 평평한 면을 다시 클릭하세요.');
                return;
            }
            const { hit, snap } = selection;
            if (
                !Number.isFinite(snap.minimumNormalAgreement)
                || snap.minimumNormalAgreement < 0.998
            ) {
                updateJointOriginPickUi(
                    '선택 영역이 완전히 평평하지 않습니다. 베벨이나 곡면이 아닌 평면을 클릭하세요.'
                );
                return;
            }

            const component = selection.component || '선택한 부품';
            let worldPoint = hit.object.localToWorld(snap.localCenter.clone());
            let worldNormal = snap.localNormal.clone()
                .transformDirection(hit.object.matrixWorld)
                .normalize();
            let worldTangent = snap.localTangent
                ? snap.localTangent.clone().transformDirection(hit.object.matrixWorld).normalize()
                : null;

            robotRoot.updateMatrixWorld(true);
            let rootPoint = robotRoot.worldToLocal(worldPoint.clone());
            const rootWorldQuaternion = new THREE.Quaternion();
            robotRoot.getWorldQuaternion(rootWorldQuaternion);
            const inverseRootQuaternion = rootWorldQuaternion.clone().invert();
            let rootNormal = worldNormal.clone().applyQuaternion(inverseRootQuaternion).normalize();
            let rootTangent = worldTangent
                ? worldTangent.clone().applyQuaternion(inverseRootQuaternion).normalize()
                : null;

            if (jointOriginPickStage === 'parent') {
                jointOriginParentSnap = {
                    component,
                    rootPoint: rootPoint.clone(),
                    rootNormal: rootNormal.clone(),
                    rootTangent: rootTangent ? rootTangent.clone() : null,
                    worldPoint: worldPoint.clone(),
                    worldNormal: worldNormal.clone(),
                    snapMode: snap.snapMode || '',
                    snapSource: snap.snapSource || 'mesh_inference',
                    cadEntityId: snap.cadEntityId || null,
                };
                jointOriginPickStage = 'child';
                jointPickTargetComponent = null;
                jointPickAllowedComponents = new Set(
                    entry.node.components || []
                );
                clearJointSnapCandidateState();
                refreshJointPickStageViewer();
                showJointSnapMarker(
                    worldPoint,
                    worldNormal,
                    snap.circleRadius,
                    true
                );
                updateJointOriginPickUi(
                    `1/2 부모 연결점 저장 완료: ${component} · 이제 2/2 자식 연결점을 선택하세요.`
                );
                return;
            }

            const childMate = {
                component,
                rootPoint: rootPoint.clone(),
                rootNormal: rootNormal.clone(),
                rootTangent: rootTangent ? rootTangent.clone() : null,
                snapMode: snap.snapMode || '',
                snapSource: snap.snapSource || 'mesh_inference',
                cadEntityId: snap.cadEntityId || null,
            };
            const parentMate = jointOriginParentSnap;
            const mateGap = parentMate
                ? parentMate.rootPoint.distanceTo(childMate.rootPoint)
                : 0;
            if (parentMate) {
                const alignedChildNormal = childMate.rootNormal.clone();
                if (alignedChildNormal.dot(parentMate.rootNormal) < 0) {
                    alignedChildNormal.negate();
                }
                const combinedNormal = parentMate.rootNormal.clone()
                    .add(alignedChildNormal);
                rootNormal = combinedNormal.lengthSq() > 1e-8
                    ? combinedNormal.normalize()
                    : parentMate.rootNormal.clone();
                rootTangent = parentMate.rootTangent
                    ? parentMate.rootTangent.clone()
                    : childMate.rootTangent;
                rootPoint = parentMate.rootPoint.clone()
                    .add(childMate.rootPoint)
                    .multiplyScalar(0.5);
                worldPoint = robotRoot.localToWorld(rootPoint.clone());
                worldNormal = rootNormal.clone()
                    .applyQuaternion(rootWorldQuaternion)
                    .normalize();
                worldTangent = rootTangent
                    ? rootTangent.clone()
                        .applyQuaternion(rootWorldQuaternion)
                        .normalize()
                    : null;
            }

            const parentFrame = previewFrameMatrixForNode(entry.parentNode);
            const parentPosition = new THREE.Vector3();
            const parentQuaternion = new THREE.Quaternion();
            const parentScale = new THREE.Vector3();
            parentFrame.decompose(parentPosition, parentQuaternion, parentScale);
            const preferredXAxis = new THREE.Vector3(1, 0, 0)
                .applyQuaternion(parentQuaternion)
                .normalize();
            const fittedFrame = jointFrameFromSurface(
                rootPoint,
                rootNormal,
                rootTangent,
                preferredXAxis
            );
            if (!fittedFrame || fittedFrame.orthogonalityError > 1e-6) {
                updateJointOriginPickUi(
                    '이 면에서 직교 좌표계를 만들지 못했습니다. 더 넓고 평평한 면을 선택하세요.'
                );
                return;
            }
            const jointWorldFrame = fittedFrame.matrix;
            const jointLocalFrame = parentFrame.clone().invert().multiply(jointWorldFrame);
            const position = new THREE.Vector3();
            const quaternion = new THREE.Quaternion();
            const scale = new THREE.Vector3();
            jointLocalFrame.decompose(position, quaternion, scale);
            const rpyEuler = new THREE.Euler().setFromQuaternion(quaternion, 'ZYX');
            const unitsPerMeter = Number(treeData._preview_units_per_meter) || 1000.0;

            saveState();
            const jointInfo = joint.joint_info || {};
            joint.joint_info = jointInfo;
            jointInfo.xyz = position.divideScalar(unitsPerMeter).toArray();
            jointInfo.rpy = [rpyEuler.x, rpyEuler.y, rpyEuler.z];
            jointInfo._manual_rpy = jointInfo.rpy.slice();
            jointInfo._preview_local_quaternion = quaternion.toArray();
            jointInfo._preview_world_quaternion = new THREE.Quaternion()
                .setFromRotationMatrix(jointWorldFrame)
                .normalize()
                .toArray();
            jointInfo._preview_world_frame_matrix = jointWorldFrame.toArray();
            jointInfo._preview_world_xyz = rootPoint.clone().divideScalar(unitsPerMeter).toArray();
            jointInfo.axis = [0, 0, 1];
            jointInfo._axis_source = snap.snapSource === 'opencascade'
                ? 'opencascade_exact_geometry'
                : '3d_surface_normal';
            jointInfo.provenance = 'user_3d_joint_pick';
            jointInfo._joint_mates = {
                mode: parentMate ? 'parent_child_surface_frames' : 'single_surface_frame',
                parent_component: parentMate ? parentMate.component : null,
                child_component: childMate.component,
                parent_root_point: parentMate
                    ? parentMate.rootPoint.toArray()
                    : null,
                child_root_point: childMate.rootPoint.toArray(),
                parent_root_normal: parentMate
                    ? parentMate.rootNormal.toArray()
                    : null,
                child_root_normal: childMate.rootNormal.toArray(),
                gap_m: mateGap / unitsPerMeter,
            };
            ensureJointMotionLimits(joint.joint_type || jointInfo.type || 'fixed', jointInfo);
            jointInfo._joint_snap = {
                component,
                mode: snap.snapSource === 'opencascade'
                    ? snap.snapMode
                    : (
                        snap.snapMode === 'circular_arc_center'
                            ? 'circular_arc_center_and_plane_normal'
                            : 'connected_planar_face_centroid_and_normal'
                    ),
                source: snap.snapSource || 'mesh_inference',
                cad_feature_type: snap.cadFeatureType || null,
                cad_entity_id: snap.cadEntityId || null,
                matched_by: snap.matchedBy || null,
                candidate_count: selection.candidateCount,
                candidate_index: selection.candidateIndex,
                depth_selected: selection.usedDepthSelection,
                circle_radius: snap.circleRadius || null,
                triangle_count: snap.triangleCount,
                root_point: rootPoint.toArray(),
                root_normal: fittedFrame.zAxis.toArray(),
                root_tangent: fittedFrame.xAxis.toArray(),
                root_y_axis: fittedFrame.yAxis.toArray(),
                orthogonality_error: fittedFrame.orthogonalityError,
                minimum_normal_agreement: snap.minimumNormalAgreement,
            };
            delete jointInfo._joint_world_matrix;
            delete jointInfo.link_world_inv_matrix;
            delete jointInfo.link_vis_xyz;
            delete jointInfo.link_vis_rpy;
            syncPickedJointLocalFrames();

            jointOriginPickMode = false;
            jointOriginPickJoint = null;
            endJointOriginPickScope();
            // The Fusion-style marker is a picking aid only. Once both mating
            // points are committed, leave the model clean instead of pinning
            // the last marker to the preview rig.
            activeJointSnapMarkerInfo = null;
            hideJointSnapMarker();
            previewRigDirty = true;
            previewControlsDirty = true;
            const pointText = jointInfo._preview_world_xyz
                .map(value => Number(value).toFixed(4))
                .join(', ');
            const snapLabel = snapDisplayLabel(snap);
            render({ previewDelay: 40 });
            updateJointOriginPickUi(
                `완료: ${component} ${snapLabel} [${pointText}] m · 빨강 X/초록 Y는 평면 안, 파랑 Z는 면 법선입니다.`
            );
            updateJointOriginPickUi(
                `완료: 부모·자식 연결 프레임을 결합했습니다. 두 연결점 간격 ${
                    (mateGap / unitsPerMeter).toFixed(5)
                } m · 조인트 원점은 두 점의 중앙입니다.`
            );
        }

        function flipSelectedJointAxis() {
            if (!selectedElement || selectedElement.type !== 'joint' || !selectedElement.jointObj) return;
            const joint = selectedElement.jointObj;
            const currentAxis = (joint.joint_info && joint.joint_info.axis) || [0, 0, 1];
            const flippedAxis = currentAxis.map(value => -Number(value || 0));
            applyJointAxisChange(joint, flippedAxis, 'user_flipped_3d_axis');
        }

        function viewerMeshPickResult(event) {
            if (!renderer || !camera || !treeData) return;
            const rect = renderer.domElement.getBoundingClientRect();
            const intersections = getViewerIntersections(event);
            let pickedMesh = intersections.length > 0 ? intersections[0].object : null;
            let component = pickedMesh
                ? Object.keys(meshDict).find(name => meshDict[name] === pickedMesh)
                : null;
            if (!component) {
                const fallback = findMeshByProjectedBounds(
                    event.clientX,
                    event.clientY,
                    rect
                );
                if (fallback) {
                    pickedMesh = fallback.mesh;
                    component = fallback.component;
                }
            }
            if (!component) return null;
            const node = findLinkByComponent(treeData, component);
            if (!node) return null;
            return { component, node, mesh: pickedMesh };
        }

        function showViewerSelectionStatus(component, node) {
            const status = document.getElementById('viewer-pick-status');
            if (!status) return;
            const count = viewerSelectedComponents.size;
            status.textContent = count > 1
                ? `부품 ${count}개 선택 · 우클릭하여 한 링크로 그룹화`
                : `${component} 선택 · 소속 링크: ${node.name}`;
            status.style.display = 'block';
            clearTimeout(status._hideTimer);
            status._hideTimer = setTimeout(() => {
                status.style.display = 'none';
            }, 2600);
        }

        function handleViewerMeshSelect(event) {
            const picked = viewerMeshPickResult(event);
            if (!picked) {
                if (!event.ctrlKey && !event.metaKey) clearSelection();
                return;
            }
            baseFootprintFrameSelected = false;
            if (baseFootprintFrameMarker) baseFootprintFrameMarker.visible = false;
            const { component, node } = picked;
            const additive = !!(event.ctrlKey || event.metaKey);
            if (!additive) viewerSelectedComponents.clear();
            if (additive && viewerSelectedComponents.has(component)) {
                viewerSelectedComponents.delete(component);
            } else {
                viewerSelectedComponents.add(component);
            }
            viewerSelectedComponent = viewerSelectedComponents.size === 1
                ? [...viewerSelectedComponents][0]
                : null;
            selectedElement = viewerSelectedComponents.size > 0
                ? { type: 'link', node, jointObj: null }
                : null;
            render({ skipPreview: true });
            if (selectedElement) revealLinkInTree(node);
            showViewerSelectionStatus(component, node);
        }

        function handleViewerMeshPick(event) {
            const picked = viewerMeshPickResult(event);
            if (!picked) return;
            baseFootprintFrameSelected = false;
            if (baseFootprintFrameMarker) baseFootprintFrameMarker.visible = false;
            const { component, node } = picked;

            if (viewerIsolatedComponent === component) {
                viewerSelectedComponent = null;
                viewerSelectedComponents.clear();
                viewerIsolatedComponent = null;
                viewerIsolatedNode = null;
                applyViewerIsolationVisibility();
                clearSelection();
                showViewerPickStatus(component, node, true);
                return;
            }

            viewerSelectedComponent = component;
            viewerSelectedComponents = new Set([component]);
            viewerIsolatedComponent = component;
            viewerIsolatedNode = null;
            applyViewerIsolationVisibility();
            selectedElement = { type: 'link', node, jointObj: null };
            render({ skipPreview: true });
            revealLinkInTree(node);
            showViewerPickStatus(component, node);
        }

        function selectedViewerLinkNodes() {
            const nodes = [];
            viewerSelectedComponents.forEach(component => {
                const node = findLinkByComponent(treeData, component);
                if (node && !nodes.includes(node)) nodes.push(node);
            });
            return nodes;
        }

        function hideViewerContextMenu() {
            const menu = document.getElementById('viewer-context-menu');
            if (menu) menu.classList.remove('visible');
        }

        function showViewerContextMenu(event) {
            if (groundFacePickMode || jointOriginPickMode) return;
            const picked = viewerMeshPickResult(event);
            if (picked && !viewerSelectedComponents.has(picked.component)) {
                viewerSelectedComponents = new Set([picked.component]);
                viewerSelectedComponent = picked.component;
                selectedElement = { type: 'link', node: picked.node, jointObj: null };
                render({ skipPreview: true });
            }
            const menu = document.getElementById('viewer-context-menu');
            const title = document.getElementById('viewer-context-title');
            const groupButton = document.getElementById('viewer-context-group');
            if (!menu || !title || !groupButton || viewerSelectedComponents.size === 0) {
                hideViewerContextMenu();
                return;
            }
            const linkCount = selectedViewerLinkNodes().length;
            title.textContent = `선택 부품 ${viewerSelectedComponents.size}개 · 링크 ${linkCount}개`;
            groupButton.disabled = linkCount < 2;
            groupButton.textContent = linkCount >= 2
                ? `선택한 ${linkCount}개 링크를 하나로 그룹화`
                : '이미 같은 링크에 포함된 부품입니다';
            menu.classList.add('visible');
            const margin = 8;
            const menuRect = menu.getBoundingClientRect();
            menu.style.left = `${Math.max(
                margin,
                Math.min(event.clientX, window.innerWidth - menuRect.width - margin)
            )}px`;
            menu.style.top = `${Math.max(
                margin,
                Math.min(event.clientY, window.innerHeight - menuRect.height - margin)
            )}px`;
            setTimeout(() => {
                document.addEventListener('pointerdown', hideViewerContextMenu, { once: true });
            }, 0);
        }

        function groupViewerSelectedComponents() {
            const nodes = selectedViewerLinkNodes();
            if (nodes.length < 2) {
                hideViewerContextMenu();
                return;
            }
            const entries = getFlatLinks(treeData, null, -1);
            const target = nodes
                .map(node => entries.find(item => item.node === node))
                .filter(Boolean)
                .sort((a, b) => a.depth - b.depth)[0]?.node;
            if (!target) return;
            saveState();
            nodes
                .filter(node => node !== target)
                .forEach(node => mergePatcherNodeInto(node, target, false));
            viewerSelectedComponent = null;
            viewerSelectedComponents.clear();
            viewerIsolatedComponent = null;
            viewerIsolatedNode = null;
            selectedElement = { type: 'link', node: target, jointObj: null };
            hideViewerContextMenu();
            render({ previewDelay: 250 });
            revealLinkInTree(target);
        }

        function highlightViewerComponentSelection() {
            applyLinkGroupColors();
            viewerSelectedComponents.forEach(component => {
                const mesh = meshDict[component];
                if (mesh) mesh.material = highlightMaterial;
                const edge = meshEdgeDict[component];
                if (edge) {
                    edge.visible = true;
                    edge.material.opacity = 0.85;
                }
            });
        }

        // 3D 뷰어 하이라이트 함수
        function highlight3DComponents(components) {
            // 아무것도 안 골랐을 때는 모두 원래대로
            if (!components || components.length === 0) {
                applyLinkGroupColors();
                return;
            }
            
            // 고른 부품 이외에는 투명하게(Ghost), 고른 부품은 파란색(Highlight)
            Object.keys(meshDict).forEach(compName => {
                if (components.includes(compName)) {
                    meshDict[compName].material = highlightMaterial;
                    if (meshEdgeDict[compName]) meshEdgeDict[compName].material.opacity = 0.72;
                } else {
                    meshDict[compName].material = ghostMaterial;
                    if (meshEdgeDict[compName]) meshEdgeDict[compName].material.opacity = 0.08;
                }
            });
        }

        function clearSelection() {
            baseFootprintFrameSelected = false;
            if (baseFootprintFrameMarker) baseFootprintFrameMarker.visible = false;
            viewerSelectedComponent = null;
            viewerSelectedComponents.clear();
            selectedElement = null;
            highlight3DComponents([]);
            updateSelectedJointFrameVisibility();
            applyViewerIsolationVisibility();
            render({ skipPreview: true });
        }

        // --- 기타 UI 변수 및 함수 ---
        let draggedNode = null;
        let draggedNodeParentList = null;
        let draggedNodeIndex = -1;
        let draggedPhysicalMaterialKey = null;
        let draggedPhysicalMaterialSource = null;
        let currentDragOverElement = null;
        let patcherNodeCounter = 1;
        let patcherConnectionDrag = null;
        let patcherCableFrame = null;
        let patcherSharpRepaintTimer = null;
        let patcherPanDrag = null;
        let patcherGroupingMode = false;
        let patcherGroupSelection = new Set();
        let patcherControllerSelectionMode = false;
        let patcherControllerJointSelection = new Set();
        let treeWireFrame = null;

        const CONTROLLER_PALETTE = [
            '#d95cff', '#28c7fa', '#ff9f43', '#44d17a', '#ff5d8f',
            '#9b7cff', '#f2d34f', '#35d0ba', '#ff704d', '#70a5ff'
        ];
        const CONTROLLER_TYPES = [
            ['joint_trajectory_controller/JointTrajectoryController', 'Joint Trajectory Controller', '시간에 따른 다관절 궤적을 실행합니다.', 'joint_trajectory_controller'],
            ['position_controllers/JointGroupPositionController', 'Joint Group Position Controller', '여러 관절에 위치값을 바로 전달합니다.', 'joint_group_position_controller'],
            ['velocity_controllers/JointGroupVelocityController', 'Joint Group Velocity Controller', '여러 관절에 속도값을 바로 전달합니다.', 'joint_group_velocity_controller'],
            ['effort_controllers/JointGroupEffortController', 'Joint Group Effort Controller', '여러 관절에 effort 값을 바로 전달합니다.', 'joint_group_effort_controller'],
            ['diff_drive_controller/DiffDriveController', 'Differential Drive Controller', '좌우 바퀴 속도를 계산하는 이동 로봇 컨트롤러입니다.', 'diff_drive_controller'],
            ['forward_command_controller/ForwardCommandController', 'Forward Command Controller', '선택한 command interface에 값을 그대로 전달합니다.', 'forward_command_controller'],
            ['position_controllers/GripperActionController', 'Position Gripper Action Controller', '단일 그리퍼 관절을 액션으로 제어합니다.', 'gripper_controller'],
            ['effort_controllers/GripperActionController', 'Effort Gripper Action Controller', '단일 그리퍼 관절을 effort 액션으로 제어합니다.', 'effort_gripper_controller'],
            ['pid_controller/PidController', 'PID Controller', '기준/상태값과 command interface 사이에 PID 제어를 적용합니다.', 'pid_controller'],
            ['joint_state_broadcaster/JointStateBroadcaster', 'Joint State Broadcaster', '관절 상태를 발행하며 모터에는 명령하지 않습니다.', 'custom_joint_state_broadcaster'],
        ];

        let historyStack = [];
        const MAX_HISTORY = 30;

        function pushHistoryEntry(entry) {
            if (!entry || !entry.kind) return;
            historyStack.push(entry);
            if (historyStack.length > MAX_HISTORY) historyStack.shift();
        }

        function saveState() {
            const snapshot = JSON.stringify(treeData, (key, value) => key === '_pivot' ? undefined : value);
            const last = historyStack[historyStack.length - 1];
            if (!last || last.kind !== 'tree' || last.snapshot !== snapshot) {
                pushHistoryEntry({kind: 'tree', snapshot});
            }
        }

        function captureViewerCameraState() {
            if (!camera || !controls) return null;
            return {
                position: camera.position.toArray(),
                quaternion: camera.quaternion.toArray(),
                target: controls.target.toArray(),
                zoom: Number(camera.zoom) || 1,
            };
        }

        function viewerCameraStatesEqual(first, second) {
            if (!first || !second) return first === second;
            const values = ['position', 'quaternion', 'target'];
            const vectorsEqual = values.every(key => (
                Array.isArray(first[key])
                && Array.isArray(second[key])
                && first[key].length === second[key].length
                && first[key].every(
                    (value, index) => Math.abs(value - second[key][index]) <= 1e-7
                )
            ));
            return vectorsEqual && Math.abs(first.zoom - second.zoom) <= 1e-7;
        }

        function restoreViewerCameraState(state) {
            if (!state || !camera || !controls) return;
            camera.position.fromArray(state.position);
            camera.quaternion.fromArray(state.quaternion);
            controls.target.fromArray(state.target);
            camera.zoom = Number(state.zoom) || 1;
            camera.updateProjectionMatrix();
            controls.update();
        }

        function beginViewerCameraGesture() {
            if (!viewerCameraGesture) {
                viewerCameraGesture = captureViewerCameraState();
            }
        }

        function endViewerCameraGesture() {
            if (!viewerCameraGesture) return;
            const before = viewerCameraGesture;
            viewerCameraGesture = null;
            const after = captureViewerCameraState();
            if (!viewerCameraStatesEqual(before, after)) {
                pushHistoryEntry({kind: 'viewer_camera', state: before});
            }
        }

        function undo() {
            if (historyStack.length === 0) return;
            const entry = historyStack.pop();
            if (entry.kind === 'viewer_camera') {
                restoreViewerCameraState(entry.state);
                return;
            }
            if (entry.kind === 'preview_joint') {
                const index = previewJointControllers.findIndex(
                    controller => controller.name === entry.jointName
                );
                if (index >= 0) setPreviewJointValue(index, Number(entry.value) || 0);
                return;
            }
            if (entry.kind === 'preview_pose') {
                restorePreviewJointPose(entry.pose);
                return;
            }
            if (entry.kind !== 'tree' || !entry.snapshot) return;

            pendingPreviewPoseRestore = capturePreviewJointPose();
            treeData = JSON.parse(entry.snapshot);
            selectedElement = null;
            highlight3DComponents([]);
            previewRigDirty = true;
            render();
            if (!applyStoredRobotRootTransform()) {
                applyRobotRootUpAxis(resolvePreviewUpAxis());
            }
        }

        document.addEventListener('keydown', function(e) {
            if (
                e.key !== 'Escape'
                && (e.target.tagName.toLowerCase() === 'input' || e.target.tagName.toLowerCase() === 'select')
            ) return;
            if (e.key === 'Escape') {
                e.preventDefault();
                hideJointSnapMarker();
                activeJointSnapMarkerInfo = null;
                baseFootprintFrameSelected = false;
                if (baseFootprintFrameMarker) baseFootprintFrameMarker.visible = false;
                if (jointOriginPickMode) {
                    cancelJointOriginPick();
                    return;
                }
                if (groundFacePickMode) {
                    groundFacePickMode = false;
                    hideGroundSnapMarker();
                    updateGroundFaceUi('바닥면 지정을 취소했습니다.');
                    return;
                }
                if (baseFootprintPickMode) {
                    baseFootprintPickMode = false;
                    hideGroundSnapMarker();
                    updateGroundFaceUi();
                    render({ skipPreview: true });
                    updateBaseFootprintPickUi('BASE FOOTPRINT 위치 지정을 취소했습니다.');
                    return;
                }
                if (patcherConnectionDrag) {
                    cancelPatcherConnection();
                    return;
                }
                if (clearViewerIsolation('전체 링크 보기로 복원했습니다.')) {
                    clearSelection();
                    return;
                }
                clearSelection();
                return;
            }
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
                e.preventDefault(); undo();
            }
        });

       function autoRename(node) {
            if (node === treeData) {
                node.name = 'base_link';
                return;
            }
           if (node.name.match(/^link_\\d+$/)) return;
            let maxLink = 0;
            const flat = getFlatLinks(treeData, null, -1);
            flat.forEach(item => {
                let match = item.node.name.match(/^link_(\\d+)$/);
                if(match) maxLink = Math.max(maxLink, parseInt(match[1]));
            });
            node.name = 'link_' + (maxLink + 1);
        }

        function showJointRenameSuggestion() {
            // 기존 팝업 제거
            let oldToast = document.getElementById('rename-toast');
            if (oldToast) oldToast.remove();

            // 0.8초 후 스르륵 나타나게 설정
            setTimeout(() => {
                const vizPane = document.getElementById('viz-pane');
                const toast = document.createElement('div');
                toast.id = 'rename-toast';
                toast.className = 'rename-hint-float';
                
                // 마인드맵 영역 중앙 상단쯤에 배치
                toast.style.top = '80px';
                toast.style.left = '50%';
                toast.style.marginLeft = '-160px'; // 가로 중앙 정렬용 (width 320px)

                toast.innerHTML = `
                    <div style="flex:1;">
                        <strong style="font-size:14px; color:#fff; display:block; margin-bottom:4px;">💡 구조가 변경되었습니다!</strong>
                        <span style="font-size:12px; color:rgba(255,255,255,0.9);">조인트 이름을 순서대로(joint_1...) 자동 재정렬하시겠습니까?</span>
                    </div>
                    <div style="display:flex; flex-direction:column; gap:5px;">
                        <button onclick="autoRenameAllJoints(); hideRenameToast();" style="background:#fff; color:#ff9800; border:none; padding:6px 10px; border-radius:4px; font-weight:bold; cursor:pointer; font-size:11px;">네, 정리할게요</button>
                        <button onclick="hideRenameToast();" style="background:transparent; color:#fff; border:1px solid rgba(255,255,255,0.5); padding:6px 10px; border-radius:4px; cursor:pointer; font-size:11px;">아니오</button>
                    </div>
                `;
                vizPane.appendChild(toast);
                
                // 스르륵 켜지는 애니메이션 트리거
                setTimeout(() => toast.classList.add('active'), 10);
            }, 800);
        }

        function hideRenameToast() {
            const toast = document.getElementById('rename-toast');
            if (toast) {
                toast.classList.remove('active');
                setTimeout(() => toast.remove(), 500);
            }
        }

        function autoRenameAllJoints() {
            saveState();
            let jCount = 1;
            const flat = getFlatLinks(treeData, null, -1);
            flat.forEach(item => {
                if (isPatcherJointActive(item.jointObj)) {
                    item.jointObj.joint_name = 'joint_' + jCount;
                    jCount++;
                }
            });
            previewControlsDirty = true;
            render(); 
        }

        function buildStructureNamingPlan() {
            if (!treeData) return null;
            const flat = getFlatLinks(treeData, null, -1);
            const visited = new Set();
            const linkMappings = [];
            const jointMappings = [];
            const previewRows = [];
            let childLinkCount = 0;
           let jointCount = 0;

            const addLink = (node, connected) => {
               if (!node || visited.has(node)) return;
               visited.add(node);
                const isBaseLink = node === treeData;
                if (!isBaseLink) childLinkCount += 1;
                const newName = isBaseLink
                    ? 'base_link'
                    : `link_${childLinkCount}`;
                linkMappings.push({node, oldName: node.name, newName, connected});
                previewRows.push({
                    kind: connected ? '링크' : '미연결 링크',
                    oldName: node.name,
                    newName,
                });
                (node.children || [])
                    .filter(child => isPatcherJointActive(child))
                    .forEach(child => {
                        jointCount += 1;
                        const newJointName = `joint_${jointCount}`;
                        jointMappings.push({
                            joint: child,
                            oldName: child.joint_name,
                            newName: newJointName,
                        });
                        previewRows.push({
                            kind: '조인트',
                            oldName: child.joint_name,
                            newName: newJointName,
                        });
                        addLink(child.link_group, true);
                    });
            };

            addLink(treeData, true);
            flat.forEach(item => {
                if (!visited.has(item.node)) addLink(item.node, false);
            });
            return {
                linkMappings,
                jointMappings,
                previewRows,
                connectedLinks: linkMappings.filter(item => item.connected).length,
                disconnectedLinks: linkMappings.filter(item => !item.connected).length,
            };
        }

        function openStructureNamingAssistant(continueExport = false, renameRequired = false) {
            structureNamingPlan = buildStructureNamingPlan();
            if (!structureNamingPlan) return;
            structureNamingContinueExport = !!continueExport;
            const modal = document.getElementById('naming-assistant-modal');
            const summary = document.getElementById('naming-assistant-summary');
            const preview = document.getElementById('naming-assistant-preview');
            const applyButton = document.getElementById('naming-assistant-apply');
            const keepButton = document.getElementById('naming-assistant-keep');
            if (applyButton) {
                applyButton.textContent = continueExport
                    ? '정리 후 URDF 생성'
                    : '이 이름으로 정렬';
            }
            if (keepButton) {
                keepButton.style.display = continueExport ? '' : 'none';
                keepButton.disabled = !!renameRequired;
                keepButton.title = renameRequired
                    ? '중복된 조인트 이름은 URDF에서 사용할 수 있어 먼저 정리해야 합니다.'
                    : '';
                keepButton.textContent = renameRequired
                    ? '중복 이름이 있어 현재 이름 사용 불가'
                    : '현재 이름 유지하고 생성';
            }
            if (summary) {
                summary.textContent = (
                    `연결 링크 ${structureNamingPlan.connectedLinks}개 · `
                    + `조인트 ${structureNamingPlan.jointMappings.length}개`
                    + (
                        structureNamingPlan.disconnectedLinks
                            ? ` · 미연결 링크 ${structureNamingPlan.disconnectedLinks}개는 뒤 번호로 정리`
                            : ''
                    )
                );
            }
            if (preview) {
                preview.innerHTML = '';
                structureNamingPlan.previewRows.forEach(item => {
                    const row = document.createElement('div');
                    row.className = 'naming-assistant-row';
                    const oldName = document.createElement('span');
                    oldName.className = 'naming-assistant-old';
                    oldName.textContent = `${item.kind} · ${item.oldName}`;
                    const arrow = document.createElement('span');
                    arrow.className = 'naming-assistant-arrow';
                    arrow.textContent = '→';
                    const newName = document.createElement('span');
                    newName.className = 'naming-assistant-new';
                    newName.textContent = item.newName;
                    row.append(oldName, arrow, newName);
                    preview.appendChild(row);
                });
            }
            if (modal) modal.style.display = 'flex';
        }

        function closeStructureNamingAssistant() {
            const modal = document.getElementById('naming-assistant-modal');
            if (modal) modal.style.display = 'none';
            structureNamingPlan = null;
            structureNamingContinueExport = false;
        }

        function applyStructureNamingAssistant() {
            if (!structureNamingPlan) return;
            const continueExport = structureNamingContinueExport;
            saveState();
            structureNamingPlan.linkMappings.forEach(item => {
                item.node.name = item.newName;
            });
            structureNamingPlan.jointMappings.forEach(item => {
                item.joint.joint_name = item.newName;
            });
            syncPatcherJointLinkNames();
            selectedElement = null;
            previewControlsDirty = true;
            previewRigDirty = true;
            closeStructureNamingAssistant();
            render();
            scheduleWorkspaceAutosave();
            if (continueExport) window.setTimeout(proceedSave, 0);
        }

        function continueExportWithoutStructureRename() {
            const keepButton = document.getElementById('naming-assistant-keep');
            if (keepButton?.disabled) return;
            closeStructureNamingAssistant();
            proceedSave();
        }

        function rootJointMode() {
            const value = document.getElementById('root-joint-mode')?.value;
            if (['world', 'base_footprint', 'none'].includes(value)) return value;
            return document.getElementById('fix-to-world')?.checked ? 'world' : 'none';
        }

        function setRootJointMode(mode) {
            const normalized = ['world', 'base_footprint', 'none'].includes(mode)
                ? mode
                : 'none';
            if (treeData) saveState();
            const modeInput = document.getElementById('root-joint-mode');
            const legacyWorldSetting = document.getElementById('fix-to-world');
            if (modeInput) modeInput.value = normalized;
            if (legacyWorldSetting) legacyWorldSetting.checked = normalized === 'world';
            if (normalized !== 'base_footprint') {
                baseFootprintPickMode = false;
                baseFootprintPanelExpanded = false;
                baseFootprintFrameSelected = false;
                hideGroundSnapMarker();
            }
            if (treeData) {
                if (normalized === 'base_footprint' && !treeData._base_footprint_frame) {
                    treeData._base_footprint_frame = {
                        world_xyz: [0, 0, 0],
                        rpy: [0, 0, 0],
                        yaw: 0,
                    };
                }
                treeData._editor_settings = {
                    ...(treeData._editor_settings || {}),
                    fix_to_world: normalized === 'world',
                    root_joint_mode: normalized,
                };
                render({ skipPreview: true });
            }
            showBaseFootprintFrameMarker();
        }

        function startBaseFootprintPlacement(event) {
            event?.preventDefault();
            event?.stopPropagation();
            if (rootJointMode() !== 'base_footprint') return;
            if (jointOriginPickMode) cancelJointOriginPick();
            groundFacePickMode = false;
            baseFootprintPickMode = true;
            baseFootprintFrameSelected = true;
            baseFootprintPanelExpanded = true;
            hideGroundSnapMarker();
            updateGroundFaceUi();
            render({ skipPreview: true });
            updateBaseFootprintPickUi(
                'BASE FOOTPRINT 전용 위치 지정 중 · 모델의 평평한 지면 기준점을 선택하세요. 기준 좌표 설정은 변경되지 않습니다.'
            );
        }

        function cancelBaseFootprintPlacement(event) {
            event?.preventDefault();
            event?.stopPropagation();
            baseFootprintPickMode = false;
            baseFootprintFrameSelected = false;
            hideGroundSnapMarker();
            if (baseFootprintFrameMarker) baseFootprintFrameMarker.visible = false;
            updateGroundFaceUi();
            render({ skipPreview: true });
            updateBaseFootprintPickUi('BASE FOOTPRINT 위치 지정을 취소했습니다.');
        }

        function setBaseFootprintCoordinate(axis, rawMillimeters) {
            const frame = treeData?._base_footprint_frame;
            const axisIndex = { x: 0, y: 1, z: 2 }[String(axis).toLowerCase()];
            const millimeters = Number(rawMillimeters);
            if (!frame || axisIndex === undefined || !Number.isFinite(millimeters)) {
                render({ skipPreview: true });
                return;
            }
            const worldXyz = Array.isArray(frame.world_xyz) && frame.world_xyz.length === 3
                ? frame.world_xyz.map(value => Number(value) || 0)
                : [0, 0, 0];
            saveState();
            worldXyz[axisIndex] = millimeters / 1000;
            frame.world_xyz = worldXyz;
            showBaseFootprintFrameMarker();
            render({ skipPreview: true });
            updateBaseFootprintPickUi(
                `BASE FOOTPRINT 위치 보정: X ${(worldXyz[0] * 1000).toFixed(1)}, Y ${(worldXyz[1] * 1000).toFixed(1)}, Z ${(worldXyz[2] * 1000).toFixed(1)} mm`
            );
        }

        function setBaseFootprintOrientation(axis, rawDegrees) {
            const frame = treeData?._base_footprint_frame;
            const axisIndex = { r: 0, p: 1, y: 2 }[String(axis).toLowerCase()];
            const degrees = Number(rawDegrees);
            if (!frame || axisIndex === undefined || !Number.isFinite(degrees)) {
                render({ skipPreview: true });
                return;
            }
            const rpy = Array.isArray(frame.rpy) && frame.rpy.length === 3
                ? frame.rpy.map(value => Number(value) || 0)
                : [0, 0, Number(frame.yaw) || 0];
            saveState();
            rpy[axisIndex] = THREE.MathUtils.degToRad(degrees);
            frame.rpy = rpy;
            frame.yaw = rpy[2];
            frame.orientation_manual = true;
            baseFootprintFrameSelected = true;
            showBaseFootprintFrameMarker();
            render({ skipPreview: true });
            updateBaseFootprintPickUi(
                `BASE FOOTPRINT 방향: R ${THREE.MathUtils.radToDeg(rpy[0]).toFixed(1)}°, P ${THREE.MathUtils.radToDeg(rpy[1]).toFixed(1)}°, Y ${THREE.MathUtils.radToDeg(rpy[2]).toFixed(1)}°`
            );
        }

        function selectBaseFootprintFrame(event) {
            event?.preventDefault();
            event?.stopPropagation();
            if (rootJointMode() !== 'base_footprint') return;
            if (jointOriginPickMode) cancelJointOriginPick();
            viewerSelectedComponent = null;
            viewerSelectedComponents.clear();
            selectedElement = null;
            highlight3DComponents([]);
            baseFootprintFrameSelected = true;
            render({ skipPreview: true });
            showBaseFootprintFrameMarker();
            updateBaseFootprintPickUi('BASE FOOTPRINT 선택됨 · 3D의 X(빨강), Y(초록), Z(파랑) 축과 아래 R·P·Y 방향값을 확인하세요.');
        }

        function toggleWorldFix(checked) {
            setRootJointMode(checked ? 'world' : 'none');
        }

        function render(options = {}) {
            const container = document.getElementById('tree');
            container.innerHTML = '';
            if (!treeData || !treeData.name) {
                container.innerHTML = '<div class="empty-state">No robot structure data</div>';
                return;
            }
            renderPatcher(container);
            
            renderGroupingList();
            updatePanel();
            updateSelectedLinkFinder();
            refreshViewerColors();
            if (!options.skipPreview) {
                schedulePreviewUpdate(options.previewDelay || 120);
            }
            scheduleWorkspaceAutosave();
        }

        function renderStructureTree(container) {
            markLegacyInventorRecoveredConnections();
            container.classList.remove('patcher-mode');
            const rootList = document.createElement('ul');
            rootList.className = 'structure-tree-root';
            rootList.appendChild(createNodeElement(treeData, null, -1, null));
            container.appendChild(rootList);
            bindTreeWireSurface();
            scheduleTreeWireRender();
        }

        function bindTreeWireSurface() {
            const pane = document.getElementById('viz-pane');
            if (!pane || pane._treeWireBound) return;
            pane._treeWireBound = true;
            pane.addEventListener('scroll', scheduleTreeWireRender, { passive: true });
            pane.addEventListener('pointermove', event => {
                if (!TREE_EDITOR_MODE || !patcherConnectionDrag) return;
                const paneRect = pane.getBoundingClientRect();
                patcherConnectionDrag.pointer = {
                    x: event.clientX - paneRect.left + pane.scrollLeft,
                    y: event.clientY - paneRect.top + pane.scrollTop,
                };
                scheduleTreeWireRender();
            });
        }

        function scheduleTreeWireRender() {
            if (!TREE_EDITOR_MODE) return;
            if (treeWireFrame) cancelAnimationFrame(treeWireFrame);
            treeWireFrame = requestAnimationFrame(() => {
                treeWireFrame = null;
                renderTreeWires();
            });
        }

        function treeWirePortPoint(pane, node, side) {
            if (!pane || !node) return null;
            const id = ensurePatcherNodeId(node);
            const port = document.querySelector(
                `.tree-wire-port.${side}[data-tree-node-id="${id}"]`
            );
            if (!port) return null;
            const paneRect = pane.getBoundingClientRect();
            const rect = port.getBoundingClientRect();
            return {
                x: rect.left - paneRect.left + pane.scrollLeft + rect.width / 2,
                y: rect.top - paneRect.top + pane.scrollTop + rect.height / 2,
            };
        }

        function treeWirePath(start, end) {
            const direction = end.x >= start.x ? 1 : -1;
            const bend = Math.max(70, Math.abs(end.x - start.x) * 0.42);
            const vertical = Math.max(25, Math.abs(end.y - start.y) * 0.18);
            return `M ${start.x} ${start.y} C ${start.x + bend * direction} ${start.y + vertical}, ${end.x - bend * direction} ${end.y - vertical}, ${end.x} ${end.y}`;
        }

        function renderTreeWires() {
            const pane = document.getElementById('viz-pane');
            if (!pane || !treeData) return;
            let svg = pane.querySelector('#tree-wire-layer');
            if (!svg) {
                svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
                svg.id = 'tree-wire-layer';
                svg.classList.add('tree-wire-layer');
                pane.insertBefore(svg, pane.firstChild);
            }
            const width = Math.max(pane.clientWidth, pane.scrollWidth);
            const height = Math.max(pane.clientHeight, pane.scrollHeight);
            svg.setAttribute('width', width);
            svg.setAttribute('height', height);
            svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
            svg.innerHTML = `
                <defs>
                    <marker id="tree-arrow-motion" viewBox="0 0 10 10" refX="8" refY="5"
                            markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                        <path d="M 0 0 L 10 5 L 0 10 z" fill="#40e1c1"></path>
                    </marker>
                    <marker id="tree-arrow-fixed" viewBox="0 0 10 10" refX="8" refY="5"
                            markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                        <path d="M 0 0 L 10 5 L 0 10 z" fill="#ffd22e"></path>
                    </marker>
                    <marker id="tree-arrow-prismatic" viewBox="0 0 10 10" refX="8" refY="5"
                            markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                        <path d="M 0 0 L 10 5 L 0 10 z" fill="#48a9ff"></path>
                    </marker>
                </defs>`;

            patcherEntries().slice(1).forEach(item => {
                if (!isPatcherJointActive(item.jointObj) || !item.parentNode) return;
                const start = treeWirePortPoint(pane, item.parentNode, 'output');
                const end = treeWirePortPoint(pane, item.node, 'input');
                if (!start || !end) return;
                const type = item.jointObj.joint_type || 'fixed';
                const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                path.setAttribute('d', treeWirePath(start, end));
                path.classList.add('tree-wire', type);
                const marker = type === 'prismatic'
                    ? 'prismatic'
                    : (type === 'fixed' ? 'fixed' : 'motion');
                path.setAttribute('marker-end', `url(#tree-arrow-${marker})`);
                if (selectedElement && selectedElement.type === 'joint'
                        && selectedElement.jointObj === item.jointObj) {
                    path.classList.add('selected');
                }
                path.addEventListener('click', event => {
                    event.stopPropagation();
                    selectElement('joint', item.node, item.jointObj);
                });
                svg.appendChild(path);
            });

            if (patcherConnectionDrag && patcherConnectionDrag.parentNode !== '__world__') {
                const start = treeWirePortPoint(
                    pane,
                    patcherConnectionDrag.parentNode,
                    'output'
                );
                const end = patcherConnectionDrag.pointer
                    || (start && { x: start.x + 90, y: start.y });
                if (start && end) {
                    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                    path.setAttribute('d', treeWirePath(start, end));
                    path.classList.add('tree-wire-temp');
                    svg.appendChild(path);
                }
            }
        }

        function armTreeConnection(event, parentNode) {
            event.preventDefault();
            event.stopPropagation();
            if (patcherConnectionDrag) {
                const sameParent = patcherConnectionDrag.parentNode === parentNode;
                cancelPatcherConnection();
                if (sameParent) return;
            }
            const pane = document.getElementById('viz-pane');
            const start = treeWirePortPoint(pane, parentNode, 'output');
            patcherConnectionDrag = {
                parentNode,
                pointer: start ? { x: start.x + 90, y: start.y } : null,
            };
            document.querySelectorAll('.tree-wire-port.input').forEach(
                port => port.classList.add('connect-target')
            );
            scheduleTreeWireRender();
        }

        function finishTreeConnection(event, childNode) {
            if (!patcherConnectionDrag) return;
            finishPatcherConnection(event, childNode);
        }

        function isRecoveredPatcherJoint(jointObj) {
            if (!jointObj) return false;
            const provenance = String(
                (jointObj.joint_info && jointObj.joint_info.provenance) || ''
            ).toLowerCase();
            return provenance.includes('recovered')
                || provenance.includes('disconnected')
                || provenance.includes('group_candidate');
        }

        function isPatcherGroupCandidate(jointObj) {
            if (!jointObj) return false;
            const provenance = String(
                (jointObj.joint_info && jointObj.joint_info.provenance) || ''
            ).toLowerCase();
            return provenance.includes('group_candidate')
                || provenance.includes('inventor_recovered_constraint');
        }

        function isPatcherJointActive(jointObj) {
            return !!jointObj && !isRecoveredPatcherJoint(jointObj);
        }

        function markLegacyInventorRecoveredConnections() {
            if (!treeData || treeData._patcher_recovery_checked) return;
            treeData._patcher_recovery_checked = true;
            const source = String(
                (treeData._import_report && treeData._import_report.source_application) || ''
            ).toLowerCase();
            const children = Array.isArray(treeData.children) ? treeData.children : [];
            const looksLikeLegacyRecovery = source.includes('inventor')
                && children.length > 3
                && children.every(child => (
                    (child.joint_type || 'fixed') === 'fixed'
                    && String(child.joint_name || '').startsWith('fixed_')
                    && String((child.joint_info || {}).provenance || '') === 'cad_metadata'
                ));
            if (!looksLikeLegacyRecovery) return;
            children.forEach(child => {
                child.joint_info = child.joint_info || {};
                child.joint_info.provenance = 'legacy_inventor_recovered_constraint';
            });
        }

        function ensurePatcherNodeId(node) {
            if (!node._patcher_id) {
                node._patcher_id = `patcher_${patcherNodeCounter++}`;
            }
            return node._patcher_id;
        }

        function patcherEntries() {
            markLegacyInventorRecoveredConnections();
            const entries = getFlatLinks(treeData, null, -1);
            entries.forEach(item => ensurePatcherNodeId(item.node));
            return entries;
        }

        function patcherConnectedState(entries) {
            const connected = new Map([[treeData, true]]);
            entries.slice(1).forEach(item => {
                connected.set(
                    item.node,
                    !!connected.get(item.parentNode) && isPatcherJointActive(item.jointObj)
                );
            });
            return connected;
        }

        function patcherActiveChildren(node) {
            return (node.children || []).filter(child => isPatcherJointActive(child));
        }

        function patcherOutputPortTop(outputIndex) {
            return 16 + outputIndex * 40;
        }

        function patcherNodeVisualHeight(node) {
            const outputPortCount = patcherActiveChildren(node).length + 1;
            const lastPortBottom = patcherOutputPortTop(outputPortCount - 1) + 13;
            return Math.max(72, lastPortBottom + 12);
        }

        function calculatePatcherLayout(entries) {
            const positions = {};
            const connected = patcherConnectedState(entries);
            const connectedNextY = new Map();
            const connectedStartX = 280;
            const connectedColumnGap = 290;
            const connectedRowGap = 32;
            const disconnectedColumnGap = 250;
            const disconnectedRowGap = 124;
            let disconnectedIndex = 0;
            entries.forEach(item => {
                const id = ensurePatcherNodeId(item.node);
                if (connected.get(item.node)) {
                    let activeDepth = 0;
                    let parent = item.parentNode;
                    while (parent) {
                        activeDepth += 1;
                        const parentItem = entries.find(candidate => candidate.node === parent);
                        parent = parentItem ? parentItem.parentNode : null;
                    }
                    const y = connectedNextY.get(activeDepth) || 54;
                    positions[id] = {
                        x: connectedStartX + activeDepth * connectedColumnGap,
                        y,
                    };
                    connectedNextY.set(
                        activeDepth,
                        y + patcherNodeVisualHeight(item.node) + connectedRowGap
                    );
                } else {
                    const column = disconnectedIndex % 5;
                    const row = Math.floor(disconnectedIndex / 5);
                    positions[id] = {
                        x: connectedStartX + column * disconnectedColumnGap,
                        y: 190 + row * disconnectedRowGap,
                    };
                    disconnectedIndex += 1;
                }
            });
            return positions;
        }

        function autoLayoutPatcher(fromButton = true) {
            if (!treeData) return;
            if (fromButton) saveState();
            treeData._patcher_positions = calculatePatcherLayout(patcherEntries());
            render({ skipPreview: true });
        }

        function patcherLayoutNeedsAttention() {
            if (!treeData) return false;
            const entries = patcherEntries();
            const expected = calculatePatcherLayout(entries);
            const current = treeData._patcher_positions || {};
            return entries.some(item => {
                const id = ensurePatcherNodeId(item.node);
                const actualPosition = current[id];
                const expectedPosition = expected[id];
                if (!actualPosition || !expectedPosition) return true;
                return Math.abs(Number(actualPosition.x) - expectedPosition.x) > 1
                    || Math.abs(Number(actualPosition.y) - expectedPosition.y) > 1;
            });
        }

        function structureNamingNeedsAttention() {
            const plan = buildStructureNamingPlan();
            if (!plan) return false;
            return plan.linkMappings.some(item => item.oldName !== item.newName)
                || plan.jointMappings.some(item => item.oldName !== item.newName);
        }

        function updatePatcherAssistantButtonStates() {
            const layoutButton = document.getElementById('patcher-auto-layout-button');
            const namingButton = document.getElementById('patcher-name-order-button');
            if (layoutButton) {
                layoutButton.classList.toggle(
                    'needs-attention',
                    patcherLayoutNeedsAttention()
                );
            }
            if (namingButton) {
                namingButton.classList.toggle(
                    'needs-attention',
                    structureNamingNeedsAttention()
                );
            }
        }

        function getPatcherView() {
            if (!treeData._patcher_view) {
                treeData._patcher_view = { x: 22, y: 18, zoom: 0.9 };
            }
            const view = treeData._patcher_view;
            view.zoom = Math.max(0.12, Math.min(1.8, Number(view.zoom) || 0.9));
            view.x = Number(view.x) || 0;
            view.y = Number(view.y) || 0;
            return view;
        }

        function applyPatcherView() {
            const viewport = document.getElementById('patcher-viewport');
            const stage = document.getElementById('patcher-canvas');
            if (!viewport || !stage || !treeData) return;
            const view = getPatcherView();
            const pixelRatio = Math.max(1, Number(window.devicePixelRatio) || 1);
            const renderX = Math.round(view.x * pixelRatio) / pixelRatio;
            const renderY = Math.round(view.y * pixelRatio) / pixelRatio;
            const renderZoom = Math.round(view.zoom * 1000) / 1000;
            stage.style.transform = `translate(${renderX}px, ${renderY}px) scale(${renderZoom})`;
            viewport.style.backgroundSize = `${28 * view.zoom}px ${28 * view.zoom}px`;
            viewport.style.setProperty('--patcher-grid-x', `${renderX % (28 * view.zoom)}px`);
            viewport.style.setProperty('--patcher-grid-y', `${renderY % (28 * view.zoom)}px`);
            const readout = document.getElementById('patcher-zoom-readout');
            if (readout) readout.textContent = `${Math.round(view.zoom * 100)}%`;
        }

        function schedulePatcherSharpRepaint() {
            if (patcherSharpRepaintTimer) clearTimeout(patcherSharpRepaintTimer);
            patcherSharpRepaintTimer = setTimeout(() => {
                patcherSharpRepaintTimer = null;
                const stage = document.getElementById('patcher-canvas');
                if (!stage) return;
                const finalTransform = stage.style.transform;
                stage.style.transform = 'none';
                void stage.offsetHeight;
                stage.style.transform = finalTransform;
                schedulePatcherCableRender();
            }, 90);
        }

        function zoomPatcher(factor, clientX = null, clientY = null) {
            const viewport = document.getElementById('patcher-viewport');
            if (!viewport || !treeData) return;
            const rect = viewport.getBoundingClientRect();
            const view = getPatcherView();
            const oldZoom = view.zoom;
            const rawZoom = Math.max(0.12, Math.min(1.8, oldZoom * factor));
            const newZoom = Math.max(0.12, Math.min(1.8, Math.round(rawZoom * 20) / 20));
            const anchorX = clientX === null ? rect.width / 2 : clientX - rect.left;
            const anchorY = clientY === null ? rect.height / 2 : clientY - rect.top;
            const worldX = (anchorX - view.x) / oldZoom;
            const worldY = (anchorY - view.y) / oldZoom;
            view.zoom = newZoom;
            view.x = anchorX - worldX * newZoom;
            view.y = anchorY - worldY * newZoom;
            applyPatcherView();
            schedulePatcherSharpRepaint();
            scheduleWorkspaceAutosave();
        }

        function fitPatcherView() {
            const viewport = document.getElementById('patcher-viewport');
            if (!viewport || !treeData) return;
            const entries = patcherEntries();
            const positions = entries.map(item => getPatcherPosition(item.node, entries));
            positions.push({ x: 42, y: 54 });
            if (rootJointMode() === 'base_footprint') {
                positions.push({ x: 42, y: 245 });
            }
            const minX = Math.min(...positions.map(position => position.x)) - 45;
            const minY = Math.min(...positions.map(position => position.y)) - 45;
            const maxX = Math.max(...positions.map(position => position.x)) + 230;
            const maxY = Math.max(...positions.map(position => position.y)) + 125;
            const rect = viewport.getBoundingClientRect();
            const zoom = Math.max(
                0.12,
                Math.min(1.25, Math.min((rect.width - 40) / (maxX - minX), (rect.height - 40) / (maxY - minY)))
            );
            treeData._patcher_view = {
                zoom,
                x: (rect.width - (maxX - minX) * zoom) / 2 - minX * zoom,
                y: (rect.height - (maxY - minY) * zoom) / 2 - minY * zoom,
            };
            applyPatcherView();
            schedulePatcherSharpRepaint();
            scheduleWorkspaceAutosave();
        }

        function setupPatcherViewport(viewport) {
            viewport.onwheel = event => {
                event.preventDefault();
                zoomPatcher(event.deltaY < 0 ? 1.12 : 1 / 1.12, event.clientX, event.clientY);
            };
            viewport.onpointerdown = event => {
                if (event.button !== 0) return;
                if (event.target.closest(
                    '.patcher-node, .patcher-joint-label, .patcher-cable, .patcher-world-fix, .patcher-footprint-settings, .patcher-controller-label, .patcher-controller-frame, .patcher-controller-border-hit'
                )) return;
                event.preventDefault();
                const view = getPatcherView();
                patcherPanDrag = {
                    startX: event.clientX,
                    startY: event.clientY,
                    viewX: view.x,
                    viewY: view.y,
                    moved: false,
                };
                viewport.classList.add('panning');
                const move = moveEvent => {
                    if (!patcherPanDrag) return;
                    if (
                        Math.abs(moveEvent.clientX - patcherPanDrag.startX) > 4
                        || Math.abs(moveEvent.clientY - patcherPanDrag.startY) > 4
                    ) patcherPanDrag.moved = true;
                    view.x = patcherPanDrag.viewX + moveEvent.clientX - patcherPanDrag.startX;
                    view.y = patcherPanDrag.viewY + moveEvent.clientY - patcherPanDrag.startY;
                    applyPatcherView();
                };
                const end = () => {
                    const wasBackgroundClick = patcherPanDrag && !patcherPanDrag.moved;
                    patcherPanDrag = null;
                    viewport.classList.remove('panning');
                    document.removeEventListener('pointermove', move);
                    document.removeEventListener('pointerup', end);
                    scheduleWorkspaceAutosave();
                    if (wasBackgroundClick) clearSelection();
                };
                document.addEventListener('pointermove', move);
                document.addEventListener('pointerup', end);
            };
        }

        function getPatcherPosition(node, entries) {
            treeData._patcher_positions = treeData._patcher_positions || {};
            const id = ensurePatcherNodeId(node);
            if (!treeData._patcher_positions[id]) {
                treeData._patcher_positions = calculatePatcherLayout(entries);
            }
            return treeData._patcher_positions[id] || { x: 300, y: 80 };
        }

        function populateLinkPartsList(container, node) {
            container.innerHTML = '';
            (node.components || []).forEach(component => {
                const row = document.createElement('div');
                row.className = 'link-part-row';
                const name = document.createElement('span');
                name.className = 'link-part-name';
                name.textContent = `- ${component}`;
                name.title = component;
                row.appendChild(name);
                if ((node.components || []).length > 1) {
                    const remove = document.createElement('button');
                    remove.type = 'button';
                    remove.className = 'link-part-remove';
                    remove.textContent = '⊖';
                    remove.title = `${component} 부품을 이 링크에서 분리`;
                    remove.setAttribute('aria-label', `${component} 부품 빼기`);
                    remove.onpointerdown = event => event.stopPropagation();
                    remove.onclick = event => {
                        event.preventDefault();
                        event.stopPropagation();
                        extractComponentFromPatcherLink(node, component);
                    };
                    row.appendChild(remove);
                }
                container.appendChild(row);
            });
        }

        function validatePatcherGraph(updateUi = true) {
            const entries = patcherEntries();
            const activeEntries = entries.filter(item => !isLinkDisabled(item.node));
            const disconnected = activeEntries.slice(1).filter(
                item => !isPatcherJointActive(item.jointObj)
            );
            const activeNames = activeEntries
                .filter(item => isPatcherJointActive(item.jointObj))
                .map(item => item.jointObj.joint_name);
            const duplicates = activeNames.filter(
                (name, index) => activeNames.indexOf(name) !== index
            );
            const incompleteLimits = activeEntries.filter(item => {
                if (!isPatcherJointActive(item.jointObj)) return false;
                if ((item.jointObj.joint_type || '') !== 'revolute') return false;
                const jointInfo = item.jointObj.joint_info || {};
                return (jointInfo._manual_limit_lower_set === true)
                    !== (jointInfo._manual_limit_upper_set === true);
            });
            const invalidLimits = activeEntries.filter(item => {
                if (!isPatcherJointActive(item.jointObj)) return false;
                if (!['revolute', 'prismatic'].includes(item.jointObj.joint_type || '')) return false;
                const jointInfo = item.jointObj.joint_info || {};
                const lower = Number(jointInfo.lower_limit);
                const upper = Number(jointInfo.upper_limit);
                return !Number.isFinite(lower)
                    || !Number.isFinite(upper)
                    || lower >= upper;
            });
            const worldRequired = !TREE_EDITOR_MODE
                && rootJointMode() !== 'none';
            const worldConnected = !worldRequired || !!treeData._patcher_world_connected;
            const footprintPlacementReady = true;
            const disabledCount = entries.filter(item => isLinkDisabled(item.node)).length;
            const result = {
                valid: disconnected.length === 0
                    && duplicates.length === 0
                    && incompleteLimits.length === 0
                    && invalidLimits.length === 0
                    && worldConnected
                    && footprintPlacementReady,
                disconnected,
                duplicates: [...new Set(duplicates)],
                incompleteLimits,
                invalidLimits,
                worldConnected,
                footprintPlacementReady,
                activeJointCount: activeNames.length,
                linkCount: activeEntries.length,
                disabledCount,
            };
            if (updateUi) {
                const status = document.getElementById('patcher-validation');
                if (status) {
                    status.classList.toggle('ok', result.valid);
                    const disabledNotice = disabledCount > 0 ? ` (비활성 ${disabledCount}개)` : '';
                    status.textContent = result.valid
                        ? `배선 완료 · 링크 ${result.linkCount}개 / 조인트 ${result.activeJointCount}개${disabledNotice}`
                        : `${worldConnected ? '' : '루트 프레임 미연결 · '}미연결 링크 ${disconnected.length}개${result.duplicates.length ? ` · 중복 조인트 이름 ${result.duplicates.length}개` : ''}${incompleteLimits.length ? ` · 리밋 미완료 ${result.incompleteLimits.length}개` : ''}${invalidLimits.length ? ` · lower ≥ upper 오류 ${invalidLimits.length}개` : ''}${disabledNotice}`;
                }
                const summary = document.getElementById('patcher-summary');
                if (summary) {
                    const disabledNotice = disabledCount > 0 ? ` · 비활성 ${disabledCount}` : '';
                    summary.textContent = `링크 ${result.linkCount} · 배선 ${result.activeJointCount} · 미연결 ${disconnected.length}${disabledNotice}`;
                }
            }
            return result;
        }

        function renderPatcher(container) {
            container.className = 'tree patcher-mode';
            const entries = patcherEntries();
            const connected = patcherConnectedState(entries);
            const shell = document.createElement('div');
            shell.className = 'patcher-shell';
            shell.innerHTML = `
                <div id="patcher-controls" class="patcher-controls">
                  <div class="patcher-toolbar">
                    <button id="patcher-auto-layout-button" type="button"
                            onclick="autoLayoutPatcher(true)">▦ 자동 정렬</button>
                    <button id="patcher-name-order-button" type="button"
                            onclick="openStructureNamingAssistant(false)">↕ 이름 정렬</button>
                    <button type="button" onclick="fitPatcherView()">⊙ 전체 보기</button>
                    <button type="button" onclick="zoomPatcher(1 / 1.18)">−</button>
                    <span id="patcher-zoom-readout" class="patcher-zoom-readout">90%</span>
                    <button type="button" onclick="zoomPatcher(1.18)">＋</button>
                    <button id="patcher-group-mode" type="button" onclick="togglePatcherGroupingMode()">▣ 그룹화</button>
                    <button id="patcher-merge-selected" type="button" onclick="mergePatcherSelection()" disabled>선택 병합</button>
                    <button id="patcher-ungroup-selected" type="button"
                            onclick="ungroupSelectedPatcherLink()" disabled>그룹 해제</button>
                    <button type="button" onclick="disconnectSelectedJoint()">✂ 선택 배선 끊기</button>
                    <button id="patcher-controller-mode" type="button"
                            onclick="togglePatcherControllerMode()">▢ 컨트롤러 지정</button>
                    <button id="patcher-material-shelf-toggle" class="patcher-material-shelf-toggle" type="button"
                            onclick="togglePatcherMaterialShelf()">▾ 재질 라이브러리</button>
                    <span id="patcher-summary" class="patcher-summary"></span>
                  </div>
                  <section id="patcher-material-shelf" class="patcher-material-shelf" hidden>
                    <div class="patcher-material-shelf-head">
                        <strong>재질 빠른 적용</strong>
                        <input id="patcher-material-shelf-search" class="patcher-material-shelf-search"
                               type="search" placeholder="재질 검색 · ABS, PLA, 알루미늄, 밀도..."
                               aria-label="빠른 적용 재질 검색"
                               oninput="filterPatcherMaterialShelf(this.value)">
                        <span class="patcher-material-shelf-hint">카드를 링크에 놓으면 모든 부품에 적용</span>
                    </div>
                    <div id="patcher-material-shelf-cards" class="patcher-material-shelf-cards"></div>
                  </section>
                </div>
                <div id="patcher-validation" class="patcher-validation"></div>
            `;
            syncPatcherMaterialShelf(shell);
            const canvas = document.createElement('div');
            canvas.id = 'patcher-canvas';
            canvas.className = 'patcher-canvas';
            const viewport = document.createElement('div');
            viewport.id = 'patcher-viewport';
            viewport.className = 'patcher-viewport';
            const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            svg.classList.add('patcher-cables');
            canvas.appendChild(svg);

            const selectedRootJointMode = rootJointMode();
            const worldFixEnabled = selectedRootJointMode !== 'none';
            const worldFixControl = document.createElement('label');
            worldFixControl.id = 'root-joint-control';
            worldFixControl.className = `patcher-world-fix${worldFixEnabled ? ' checked-state' : ''}`;
            worldFixControl.title = '루트 링크를 WORLD 또는 BASE FOOTPRINT 기준 프레임에 연결합니다.';
            worldFixControl.onpointerdown = event => event.stopPropagation();
            worldFixControl.onclick = event => event.stopPropagation();
            worldFixControl.innerHTML = `
                <select id="root-joint-mode-select" onchange="setRootJointMode(this.value)">
                    <option value="world" ${selectedRootJointMode === 'world' ? 'selected' : ''}>world_joint 생성</option>
                    <option value="base_footprint" ${selectedRootJointMode === 'base_footprint' ? 'selected' : ''}>base_footprint_joint 생성</option>
                    <option value="none" ${selectedRootJointMode === 'none' ? 'selected' : ''}>루트 조인트 없음</option>
                </select>
            `;
            canvas.appendChild(worldFixControl);

            const world = document.createElement('div');
            world.className = 'patcher-node world-node';
            if (selectedRootJointMode === 'base_footprint') {
                world.classList.add('footprint-with-settings');
                if (baseFootprintFrameSelected) world.classList.add('base-footprint-selected');
            }
            if (!treeData._patcher_world_connected) world.classList.add('disconnected-world');
            if (!worldFixEnabled) world.classList.add('world-disabled');
            world.dataset.patcherId = '__world__';
            world.style.left = '42px';
            world.style.top = '54px';
            world.onclick = event => {
                if (event.target.closest('.patcher-port')) return;
                if (selectedRootJointMode === 'base_footprint') selectBaseFootprintFrame(event);
            };
            const rootFrameTitle = selectedRootJointMode === 'world'
                ? '🌍 WORLD'
                : selectedRootJointMode === 'base_footprint'
                    ? '⬡ BASE FOOTPRINT'
                    : '◇ FREE ROOT';
            world.innerHTML = `${rootFrameTitle}<div style="font-size:9px;color:#9bdca4;margin-top:5px;">${
                worldFixEnabled
                    ? (treeData._patcher_world_connected
                        ? (selectedRootJointMode === 'base_footprint'
                            ? 'base_footprint_joint · 좌표 입력'
                            : 'world_joint · fixed')
                        : '루트를 직접 연결하세요')
                    : '기준 프레임 연결 없음'
            }</div>`;
            const worldOutput = document.createElement('button');
            worldOutput.type = 'button';
            worldOutput.className = 'patcher-port output';
            worldOutput.setAttribute('aria-label', 'WORLD 출력 포트');
            worldOutput.title = treeData._patcher_world_connected
                ? '더블클릭하면 루트 프레임 배선을 끊습니다'
                : '기준 프레임에서 루트 링크 연결을 시작합니다';
            worldOutput.disabled = !worldFixEnabled;
            worldOutput.onpointerdown = event => beginPatcherConnection(event, '__world__');
            worldOutput.onclick = event => armPatcherConnectionByClick(event, '__world__');
            worldOutput.ondblclick = event => disconnectPatcherPort(event, treeData, null);
            world.appendChild(worldOutput);
            canvas.appendChild(world);

            if (selectedRootJointMode === 'base_footprint') {
                const footprintFrame = treeData._base_footprint_frame || {
                    world_xyz: [0, 0, 0], rpy: [0, 0, 0], yaw: 0,
                };
                const footprintMillimeters = Array.isArray(footprintFrame.world_xyz)
                    ? footprintFrame.world_xyz.map(value => Number(value || 0) * 1000)
                    : [0, 0, 0];
                const footprintRpy = Array.isArray(footprintFrame.rpy) && footprintFrame.rpy.length === 3
                    ? footprintFrame.rpy.map(value => Number(value) || 0)
                    : [0, 0, Number(footprintFrame.yaw) || 0];
                const footprintDegrees = footprintRpy.map(value => THREE.MathUtils.radToDeg(value));
                const settings = document.createElement('section');
                settings.id = 'base-footprint-settings';
                settings.className = 'patcher-footprint-settings';
                if (baseFootprintFrameSelected) settings.classList.add('base-footprint-selected');
                settings.onpointerdown = event => {
                    event.stopPropagation();
                    if (!baseFootprintFrameSelected) {
                        baseFootprintFrameSelected = true;
                        world.classList.add('base-footprint-selected');
                        settings.classList.add('base-footprint-selected');
                        showBaseFootprintFrameMarker();
                    }
                };
                settings.onclick = event => event.stopPropagation();
                settings.innerHTML = `
                    <div class="patcher-footprint-settings-heading">
                        <span>BASE FOOTPRINT 좌표</span>
                        <span>ROS XYZ · mm</span>
                    </div>
                    <div class="patcher-footprint-offset-fields">
                        ${['x', 'y', 'z'].map((axis, index) => `
                            <label>${axis.toUpperCase()}
                                <input type="number" step="1" value="${Number(footprintMillimeters[index].toFixed(3))}"
                                       onchange="setBaseFootprintCoordinate('${axis}', this.value)">
                            </label>
                        `).join('')}
                    </div>
                    <div class="patcher-footprint-settings-heading" style="margin-top:9px;">
                        <span>BASE FOOTPRINT 방향</span>
                        <span>ROS RPY · °</span>
                    </div>
                    <div class="patcher-footprint-offset-fields">
                        ${['r', 'p', 'y'].map((axis, index) => `
                            <label>${axis.toUpperCase()}
                                <input type="number" step="1" value="${Number(footprintDegrees[index].toFixed(3))}"
                                       onchange="setBaseFootprintOrientation('${axis}', this.value)">
                            </label>
                        `).join('')}
                    </div>
                `;
                canvas.appendChild(settings);
            }

            entries.forEach(item => {
                const nodeElement = createPatcherNode(item, entries, connected);
                canvas.appendChild(nodeElement);
            });

            const positions = treeData._patcher_positions || calculatePatcherLayout(entries);
            const allPositions = Object.values(positions);
            const maxX = Math.max(1420, ...allPositions.map(position => position.x + 270));
            const maxY = Math.max(720, ...allPositions.map(position => position.y + 180));
            canvas.style.width = `${Math.max(3200, maxX)}px`;
            canvas.style.height = `${Math.max(2000, maxY)}px`;
            if (entries.length === 1) {
                const note = document.createElement('div');
                note.className = 'patcher-empty-note';
                note.textContent = '링크가 하나뿐입니다. 조립품을 불러오면 이곳에 링크 노드가 표시됩니다.';
                canvas.appendChild(note);
            }
            viewport.appendChild(canvas);
            const validationStatus = shell.querySelector('#patcher-validation');
            if (validationStatus) viewport.appendChild(validationStatus);
            shell.appendChild(viewport);
            container.appendChild(shell);
            setupPatcherViewport(viewport);
            applyPatcherView();
            updatePatcherGroupingUi();
            updatePatcherAssistantButtonStates();
            validatePatcherGraph(true);
            schedulePatcherCableRender();
        }

        function createPatcherNode(item, entries, connected) {
            const { node, jointObj } = item;
            const id = ensurePatcherNodeId(node);
            const position = getPatcherPosition(node, entries);
            const element = document.createElement('div');
            element.className = 'patcher-node';
            element._petasosNode = node;
            element.dataset.patcherId = id;
            element.style.left = `${position.x}px`;
            element.style.top = `${position.y}px`;
            element.style.minHeight = `${patcherNodeVisualHeight(node)}px`;
            const disabled = isLinkDisabled(node);
            if (!connected.get(node)) element.classList.add('disconnected');
            if (disabled) {
                element.classList.add('disabled');
            }
            if (patcherGroupSelection.has(node)) {
                element.classList.add('group-selected');
                if (getPatcherGroupTarget() === node) element.classList.add('group-target');
            }

            const box = document.createElement('div');
            box.className = 'link-box selectable';
            box._petasosNode = node;
            box.style.minHeight = `${patcherNodeVisualHeight(node)}px`;
            box.setAttribute('role', 'button');
            box.setAttribute('aria-label', `${node.name} 링크 노드`);
            box.tabIndex = 0;
            if (node.is_finalized) box.classList.add('finalized');
            if (disabled) box.classList.add('disabled');
            if (selectedElement && selectedElement.type === 'link' && selectedElement.node === node) {
                box.classList.add('selected');
            }

            const header = document.createElement('div');
            header.className = 'patcher-node-header';
            const colorDot = document.createElement('span');
            colorDot.className = 'link-color-dot';
            colorDot.style.background = colorToCss(getLinkGroupColor(node));
            const title = document.createElement('span');
            title.className = 'patcher-node-title';
            title.textContent = node.name;
            title.title = '더블클릭하여 링크 이름 수정';
            title.ondblclick = event => startPatcherLinkRename(event, node, title);
            const renameButton = document.createElement('button');
            renameButton.type = 'button';
            renameButton.className = 'patcher-node-rename';
            renameButton.textContent = '✎';
            renameButton.title = '링크 이름 수정';
            renameButton.onpointerdown = event => event.stopPropagation();
            renameButton.onclick = event => startPatcherLinkRename(event, node, title);
            const toggleActiveButton = document.createElement('button');
            toggleActiveButton.type = 'button';
            toggleActiveButton.className = 'patcher-node-toggle';
            updateToggleActiveButtonUi(toggleActiveButton, disabled, node.name);
            if (node === treeData) {
                toggleActiveButton.style.display = 'none';
            }
            toggleActiveButton.onpointerdown = event => event.stopPropagation();
            toggleActiveButton.onclick = event => {
                event.preventDefault();
                event.stopPropagation();
                toggleLinkActive(node);
            };
            const ungroupButton = document.createElement('button');
            ungroupButton.type = 'button';
            ungroupButton.className = 'patcher-node-ungroup';
            ungroupButton.textContent = '분리';
            ungroupButton.title = '묶인 부품을 각각의 카드로 그룹 해제';
            ungroupButton.style.display = (node.components || []).length > 1 ? '' : 'none';
            ungroupButton.onpointerdown = event => event.stopPropagation();
            ungroupButton.onclick = event => {
                event.preventDefault();
                event.stopPropagation();
                ungroupPatcherLink(node);
            };
            const state = document.createElement('span');
            state.className = 'patcher-node-state';
            if (disabled) {
                state.textContent = '비활성';
                state.classList.add('disabled-state');
            } else {
                state.textContent = node.is_finalized
                    ? 'LINK'
                    : (
                        item.node === treeData && treeData._patcher_world_connected
                            ? 'ROOT'
                            : (
                                isPatcherJointActive(jointObj)
                                    ? (jointObj.joint_type || 'fixed')
                                    : (isPatcherGroupCandidate(jointObj) ? '묶음 후보' : '미연결')
                            )
                    );
            }
            header.append(colorDot, title, renameButton, toggleActiveButton, ungroupButton, state);
            box.appendChild(header);

            const partsDiv = document.createElement('div');
            partsDiv.className = 'link-parts';
            partsDiv.innerHTML = `<span>${node.components.length} Parts</span><span class="expand-icon">▼</span>`;
            const partsList = document.createElement('div');
            partsList.className = 'link-parts-list';
            populateLinkPartsList(partsList, node);
            partsDiv.onclick = event => {
                event.stopPropagation();
                if (patcherGroupingMode) {
                    togglePatcherGroupNode(node, element);
                    return;
                }
                box.classList.toggle('expanded');
            };
            box.append(partsDiv, partsList);
            box.onclick = event => {
                event.stopPropagation();
                if (patcherGroupingMode) {
                    togglePatcherGroupNode(node, element);
                } else {
                    selectElement('link', node, null);
                }
            };
            box.onkeydown = event => {
                if (event.key !== 'Enter' && event.key !== ' ') return;
                event.preventDefault();
                box.click();
            };
            attachPatcherNodeMove(box, node, element);
            attachPhysicalMaterialDropEvents(element, node);
            element.appendChild(box);

            const input = document.createElement('button');
            input.type = 'button';
            input.className = 'patcher-port input';
            input.setAttribute('aria-label', `${node.name} 입력 포트`);
            input.title = (
                isPatcherJointActive(jointObj)
                || (node === treeData && treeData._patcher_world_connected)
            )
                ? '더블클릭하면 이 배선을 끊습니다'
                : '부모 링크의 출력 포트를 연결하세요';
            input.onpointerup = event => finishPatcherConnection(event, node);
            input.onclick = event => finishPatcherConnection(event, node);
            input.ondblclick = event => disconnectPatcherPort(event, node, jointObj);
            element.appendChild(input);
            const activeChildren = patcherActiveChildren(node);
            activeChildren.forEach((childJoint, outputIndex) => {
                const childNode = childJoint.link_group;
                const childId = ensurePatcherNodeId(childNode);
                const output = document.createElement('button');
                output.type = 'button';
                output.className = 'patcher-port output connected-output';
                output.dataset.outputKey = childId;
                output.style.top = `${patcherOutputPortTop(outputIndex)}px`;
                output.setAttribute(
                    'aria-label',
                    `${node.name} → ${childNode.name} 분기 출력 ${outputIndex + 1}`
                );
                output.title = `${childNode.name}로 연결된 ${childJoint.joint_name}`;
                output.onpointerdown = event => {
                    event.preventDefault();
                    event.stopPropagation();
                };
                output.onclick = event => {
                    event.preventDefault();
                    event.stopPropagation();
                    selectElement('joint', childNode, childJoint);
                };
                output.ondblclick = event => {
                    disconnectPatcherPort(event, childNode, childJoint);
                };
                element.appendChild(output);
            });

            const addOutput = document.createElement('button');
            addOutput.type = 'button';
            addOutput.className = 'patcher-port output add-output';
            addOutput.dataset.outputKey = '__new__';
            addOutput.style.top = `${patcherOutputPortTop(activeChildren.length)}px`;
            addOutput.textContent = '+';
            addOutput.setAttribute('aria-label', `${node.name} 새 분기 출력 포트`);
            addOutput.title = '새 자식 링크를 연결합니다';
            addOutput.onpointerdown = event => beginPatcherConnection(event, node, '__new__');
            addOutput.onclick = event => armPatcherConnectionByClick(event, node, '__new__');
            element.appendChild(addOutput);
            return element;
        }

        function getPatcherGroupTarget() {
            if (patcherGroupSelection.size === 0) return null;
            const entries = patcherEntries();
            return [...patcherGroupSelection]
                .map(node => entries.find(item => item.node === node))
                .filter(Boolean)
                .sort((a, b) => a.depth - b.depth)[0]?.node || null;
        }

        function updatePatcherGroupingUi() {
            const modeButton = document.getElementById('patcher-group-mode');
            const mergeButton = document.getElementById('patcher-merge-selected');
            const ungroupButton = document.getElementById('patcher-ungroup-selected');
            if (modeButton) {
                modeButton.textContent = patcherGroupingMode ? '✕ 그룹화 취소' : '▣ 그룹화';
                modeButton.style.borderColor = patcherGroupingMode ? '#d95cff' : '';
            }
            if (mergeButton) {
                mergeButton.disabled = patcherGroupSelection.size < 2;
                mergeButton.textContent = patcherGroupSelection.size >= 2
                    ? `선택 ${patcherGroupSelection.size}개 병합`
                    : '선택 병합';
            }
            if (ungroupButton) {
                const selectedNode = selectedElement && selectedElement.type === 'link'
                    ? selectedElement.node
                    : null;
                ungroupButton.disabled = !selectedNode
                    || (selectedNode.components || []).length < 2;
            }
            updatePatcherControllerUi();
        }

        function robotControllers() {
            if (!treeData) return [];
            if (!Array.isArray(treeData._controllers)) treeData._controllers = [];
            treeData._controllers.forEach((controller, index) => {
                if (!controller.color) controller.color = CONTROLLER_PALETTE[index % CONTROLLER_PALETTE.length];
                if (!controller.type) controller.type = CONTROLLER_TYPES[0][0];
                if (!controller.settings || typeof controller.settings !== 'object') controller.settings = {};
            });
            const usedNames = new Set(treeData._controllers
                .map(controller => String(controller.name || ''))
                .filter(name => name && !/^controller_\d+$/.test(name)));
            treeData._controllers.forEach(controller => {
                if (!/^controller_\d+$/.test(String(controller.name || ''))) return;
                const option = CONTROLLER_TYPES.find(candidate => candidate[0] === controller.type) || CONTROLLER_TYPES[0];
                const baseName = option[3];
                let normalized = baseName;
                let suffix = 2;
                while (usedNames.has(normalized)) normalized = `${baseName}_${suffix++}`;
                controller.name = normalized;
                usedNames.add(normalized);
            });
            return treeData._controllers;
        }

        function controllerColorRgba(hex, alpha) {
            const value = String(hex || '').replace('#', '');
            if (!/^[0-9a-fA-F]{6}$/.test(value)) return `rgba(217,92,255,${alpha})`;
            const number = parseInt(value, 16);
            return `rgba(${(number >> 16) & 255},${(number >> 8) & 255},${number & 255},${alpha})`;
        }

        function nextControllerColor() {
            const used = new Set(robotControllers().map(controller => String(controller.color || '').toLowerCase()));
            return CONTROLLER_PALETTE.find(color => !used.has(color.toLowerCase()))
                || CONTROLLER_PALETTE[robotControllers().length % CONTROLLER_PALETTE.length];
        }

        function updatePatcherControllerUi() {
            const button = document.getElementById('patcher-controller-mode');
            if (!button) return;
            const count = patcherControllerJointSelection.size;
            button.textContent = patcherControllerSelectionMode
                ? (count > 0 ? `✓ 컨트롤러 생성 (${count})` : '✕ 컨트롤러 지정 취소')
                : '▢ 컨트롤러 지정';
            button.style.borderColor = patcherControllerSelectionMode ? '#d95cff' : '';
            button.style.color = patcherControllerSelectionMode ? '#ffd8ff' : '';
        }

        function nextControllerName() {
            const used = new Set(robotControllers().map(controller => String(controller.name || '')));
            let index = 1;
            while (used.has(`controller_${index}`)) index += 1;
            return `controller_${index}`;
        }

        function controllerNameForType(type, currentController = null) {
            const option = CONTROLLER_TYPES.find(candidate => candidate[0] === type) || CONTROLLER_TYPES[0];
            const baseName = option[3];
            const used = new Set(robotControllers()
                .filter(controller => controller !== currentController)
                .map(controller => String(controller.name || '')));
            if (!used.has(baseName)) return baseName;
            let suffix = 2;
            while (used.has(`${baseName}_${suffix}`)) suffix += 1;
            return `${baseName}_${suffix}`;
        }

        function togglePatcherControllerMode() {
            if (patcherControllerSelectionMode && patcherControllerJointSelection.size > 0) {
                createControllerFromPatcherSelection();
                return;
            }
            patcherControllerSelectionMode = !patcherControllerSelectionMode;
            patcherControllerJointSelection.clear();
            if (patcherControllerSelectionMode) {
                patcherGroupingMode = false;
                patcherGroupSelection.clear();
            }
            render({ skipPreview: true });
            const status = document.getElementById('patcher-validation');
            if (status && patcherControllerSelectionMode) {
                status.textContent = '가동 조인트 이름 라벨을 선택한 뒤 컨트롤러 생성 버튼을 누르세요.';
            }
        }

        function toggleControllerJointSelection(jointObj) {
            if (!jointObj || jointObj.joint_type === 'fixed') {
                const status = document.getElementById('patcher-validation');
                if (status) status.textContent = 'fixed 조인트는 동작 컨트롤러에 넣을 수 없습니다.';
                return;
            }
            if (patcherControllerJointSelection.has(jointObj)) {
                patcherControllerJointSelection.delete(jointObj);
            } else {
                patcherControllerJointSelection.add(jointObj);
            }
            render({ skipPreview: true });
        }

        function createControllerFromPatcherSelection() {
            const jointNames = [...patcherControllerJointSelection]
                .filter(joint => joint && joint.joint_type !== 'fixed')
                .map(joint => joint.joint_name);
            if (!jointNames.length) return;
            saveState();
            const selectedNames = new Set(jointNames);
            const controllers = robotControllers();
            controllers.forEach(controller => {
                controller.joints = (controller.joints || []).filter(name => !selectedNames.has(name));
            });
            treeData._controllers = controllers.filter(controller => (controller.joints || []).length > 0);
            const controller = {
                id: `controller_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
                name: controllerNameForType('joint_trajectory_controller/JointTrajectoryController'),
                type: 'joint_trajectory_controller/JointTrajectoryController',
                color: nextControllerColor(),
                settings: {},
                joints: jointNames,
            };
            treeData._controllers.push(controller);
            patcherControllerSelectionMode = false;
            patcherControllerJointSelection.clear();
            selectedElement = { type: 'controller', controller };
            render({ skipPreview: true });
        }

        function selectRobotController(event, controller) {
            event?.preventDefault();
            event?.stopPropagation();
            patcherControllerSelectionMode = false;
            patcherControllerJointSelection.clear();
            baseFootprintFrameSelected = false;
            if (baseFootprintFrameMarker) baseFootprintFrameMarker.visible = false;
            viewerSelectedComponent = null;
            viewerSelectedComponents.clear();
            selectedElement = { type: 'controller', controller };
            const jointNames = new Set(controller?.joints || []);
            const components = [];
            patcherEntries().forEach(entry => {
                if (entry.jointObj && jointNames.has(entry.jointObj.joint_name) && entry.node && Array.isArray(entry.node.components)) {
                    components.push(...entry.node.components);
                }
            });
            if (components.length > 0) {
                highlight3DComponents(components);
            } else {
                applyLinkGroupColors();
            }
            updateSelectedJointFrameVisibility();
            render({ skipPreview: true });
        }

        function updateSelectedControllerName(rawName) {
            const controller = selectedElement?.controller;
            if (!controller) return;
            const normalized = String(rawName || '').trim().replace(/[^A-Za-z0-9_]/g, '_');
            if (!normalized) return render({ skipPreview: true });
            const duplicate = robotControllers().some(
                candidate => candidate !== controller && candidate.name === normalized
            );
            if (duplicate) {
                alert('같은 컨트롤러 이름이 이미 있습니다.');
                return render({ skipPreview: true });
            }
            saveState();
            controller.name = normalized;
            render({ skipPreview: true });
        }

        function controllerRequiredCommandInterface(controller) {
            const type = controller?.type || CONTROLLER_TYPES[0][0];
            if (type.includes('Velocity') || type.includes('diff_drive')) return 'velocity';
            if (type.includes('Effort')) return 'effort';
            if (type.includes('JointStateBroadcaster')) return null;
            if (type.includes('ForwardCommand') || type.includes('PidController')) {
                return controller.settings?.command_interface || 'position';
            }
            return 'position';
        }

        function applyControllerInterfaceToJoints(controller) {
            const commandInterface = controllerRequiredCommandInterface(controller);
            if (!commandInterface) return;
            const names = new Set(controller.joints || []);
            patcherEntries().forEach(entry => {
                if (!entry.jointObj || !names.has(entry.jointObj.joint_name)) return;
                entry.jointObj.joint_info = entry.jointObj.joint_info || {};
                entry.jointObj.joint_info.command_interface = commandInterface;
                if ((controller.type || '').includes('diff_drive')) {
                    entry.jointObj.joint_info.state_interfaces = ['position', 'velocity'];
                }
            });
        }

        function automaticDiffDriveSides(joints) {
            const positioned = joints.map(name => {
                const entry = patcherEntries().find(item => item.jointObj?.joint_name === name);
                return { name, y: Number(entry?.jointObj?.joint_info?.xyz?.[1]) };
            });
            if (positioned.length >= 2 && positioned.every(item => Number.isFinite(item.y))) {
                positioned.sort((a, b) => a.y - b.y);
                const split = Math.max(1, Math.floor(positioned.length / 2));
                return {
                    left: positioned.slice(split).map(item => item.name),
                    right: positioned.slice(0, split).map(item => item.name),
                };
            }
            const split = Math.max(1, Math.ceil(joints.length / 2));
            return { left: joints.slice(0, split), right: joints.slice(split) };
        }

        function automaticWheelSeparation(left, right) {
            const yFor = name => {
                const entry = patcherEntries().find(item => item.jointObj?.joint_name === name);
                return Number(entry?.jointObj?.joint_info?.xyz?.[1]);
            };
            const leftY = left.map(yFor), rightY = right.map(yFor);
            if (!leftY.length || !rightY.length || ![...leftY, ...rightY].every(Number.isFinite)) return null;
            const average = values => values.reduce((sum, value) => sum + value, 0) / values.length;
            const result = Math.abs(average(leftY) - average(rightY));
            return result > 1e-9 ? result : null;
        }

        function updateSelectedControllerType(type) {
            const controller = selectedElement?.controller;
            if (!controller || !CONTROLLER_TYPES.some(option => option[0] === type)) return;
            saveState();
            controller.type = type;
            controller.name = controllerNameForType(type, controller);
            controller.settings = controller.settings || {};
            if (type.includes('diff_drive')) {
                const joints = controller.joints || [];
                const sides = automaticDiffDriveSides(joints);
                controller.settings.left_wheel_names = sides.left;
                controller.settings.right_wheel_names = sides.right;
                controller.settings.wheel_sides_manual = false;
                controller.settings.wheel_separation = automaticWheelSeparation(sides.left, sides.right);
                controller.settings.wheel_separation_manual = false;
                controller.settings.position_feedback = false;
                delete controller.settings.wheel_radius;
            } else if (type.includes('GripperActionController')) {
                controller.settings.joint ||= (controller.joints || [])[0] || '';
                controller.settings.goal_tolerance ??= 0.01;
                controller.settings.max_effort ??= 0.0;
            } else if (type.includes('PidController')) {
                controller.settings.command_interface ||= 'position';
                controller.settings.reference_and_state_interface ||= 'position';
                controller.settings.p ??= 1.0;
                controller.settings.i ??= 0.0;
                controller.settings.d ??= 0.0;
            } else if (type.includes('ForwardCommand')) {
                controller.settings.command_interface ||= 'position';
            }
            applyControllerInterfaceToJoints(controller);
            render({ skipPreview: true });
        }

        function updateSelectedControllerSetting(key, value, numeric = false) {
            const controller = selectedElement?.controller;
            if (!controller) return;
            saveState();
            controller.settings = controller.settings || {};
            controller.settings[key] = numeric ? Number(value) : value;
            if (key === 'wheel_separation') controller.settings.wheel_separation_manual = true;
            if (key === 'wheel_radius') controller.settings.wheel_radius_manual = true;
            if (key === 'command_interface') applyControllerInterfaceToJoints(controller);
            render({ skipPreview: true });
        }

        function updateDiffDriveSide(jointName, side) {
            const controller = selectedElement?.controller;
            if (!controller) return;
            saveState();
            controller.settings = controller.settings || {};
            const left = new Set(controller.settings.left_wheel_names || []);
            const right = new Set(controller.settings.right_wheel_names || []);
            left.delete(jointName); right.delete(jointName);
            (side === 'left' ? left : right).add(jointName);
            controller.settings.left_wheel_names = [...left];
            controller.settings.right_wheel_names = [...right];
            controller.settings.wheel_sides_manual = true;
            if (!controller.settings.wheel_separation_manual) {
                controller.settings.wheel_separation = automaticWheelSeparation([...left], [...right]);
            }
            render({ skipPreview: true });
        }

        function deleteSelectedController() {
            const controller = selectedElement?.controller;
            if (!controller) return;
            saveState();
            treeData._controllers = robotControllers().filter(candidate => candidate !== controller);
            selectedElement = null;
            render({ skipPreview: true });
        }

        function controllerTypeEditorHtml(controller) {
            const type = controller.type || CONTROLLER_TYPES[0][0];
            const selectedOption = CONTROLLER_TYPES.find(option => option[0] === type) || CONTROLLER_TYPES[0];
            return `
                <div class="joint-property-section-title">CONTROLLER TYPE</div>
                <select class="form-control" onchange="updateSelectedControllerType(this.value)">
                    ${CONTROLLER_TYPES.map(option => `<option value="${option[0]}" ${option[0] === type ? 'selected' : ''}>${option[1]}</option>`).join('')}
                </select>
                <div style="margin-top:5px;color:#92aab5;font-size:9px;line-height:1.45;word-break:break-all;">${escapeHtmlText(type)}<br>${escapeHtmlText(selectedOption[2])}</div>`;
        }

        function controllerSpecificSettingsHtml(controller, joints) {
            const settings = controller.settings || {};
            const type = controller.type || CONTROLLER_TYPES[0][0];
            const interfaceOptions = ['position', 'velocity', 'effort'].map(value =>
                `<option value="${value}" ${settings.command_interface === value ? 'selected' : ''}>${value}</option>`
            ).join('');
            let specific = '';
            if (type.includes('diff_drive')) {
                const left = new Set(settings.left_wheel_names || []);
                const automaticSeparation = automaticWheelSeparation(
                    [...left], joints.filter(name => !left.has(name))
                );
                specific = `
                    ${joints.length < 2 ? '<div class="info-box" style="margin-top:10px;border-color:#d08b38;color:#ffd69b;">차동구동에는 LEFT와 RIGHT에 배정할 조인트가 최소 2개 필요합니다.</div>' : ''}
                    <div class="joint-property-section-title" style="margin-top:12px;">DRIVE GEOMETRY · m</div>
                    <div class="joint-property-grid two-column">
                        <label>Wheel Separation<input type="number" step="0.001" class="form-control"
                            value="${Number(settings.wheel_separation ?? automaticSeparation ?? 0)}"
                            onchange="updateSelectedControllerSetting('wheel_separation', this.value, true)"></label>
                        <label>Wheel Radius<input type="number" step="0.001" class="form-control"
                            min="0.000001" value="${settings.wheel_radius == null ? '' : Number(settings.wheel_radius)}" placeholder="실측값 입력"
                            onchange="updateSelectedControllerSetting('wheel_radius', this.value, true)"></label>
                    </div>
                    <div style="margin-top:5px;color:#92aab5;font-size:9px;line-height:1.45;">Wheel Separation은 CAD 조인트 Y 좌표(+Y=LEFT)로 계산됩니다. Wheel Radius는 내보낼 때 휠 CAD 메시에서 자동 계산하며, 메시가 없거나 직접 고정하려면 실측값을 입력하세요.</div>
                    <div style="margin-top:9px;font-size:9px;color:#9fadb4;">Left / Right Wheels</div>
                    <div class="parts-list" style="margin-top:4px;">
                        ${joints.map(name => `<label style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
                            <span>${escapeHtmlText(name)}</span>
                            <select class="form-control" style="width:82px;padding:3px;" onchange="updateDiffDriveSide('${escapeHtmlText(name)}', this.value)">
                                <option value="left" ${left.has(name) ? 'selected' : ''}>LEFT</option>
                                <option value="right" ${!left.has(name) ? 'selected' : ''}>RIGHT</option>
                            </select>
                        </label>`).join('')}
                    </div>`;
            } else if (type.includes('GripperActionController')) {
                specific = `
                    <div class="joint-property-section-title" style="margin-top:12px;">GRIPPER</div>
                    <label>Controlled Joint<select class="form-control" onchange="updateSelectedControllerSetting('joint', this.value)">
                        ${joints.map(name => `<option value="${escapeHtmlText(name)}" ${settings.joint === name ? 'selected' : ''}>${escapeHtmlText(name)}</option>`).join('')}
                    </select></label>
                    <div class="joint-property-grid two-column">
                        <label>Goal Tolerance<input type="number" step="0.001" class="form-control" value="${Number(settings.goal_tolerance ?? 0.01)}" onchange="updateSelectedControllerSetting('goal_tolerance', this.value, true)"></label>
                        <label>Max Effort<input type="number" step="0.1" class="form-control" value="${Number(settings.max_effort ?? 0)}" onchange="updateSelectedControllerSetting('max_effort', this.value, true)"></label>
                    </div>`;
            } else if (type.includes('ForwardCommand')) {
                specific = `<label style="margin-top:10px;">Command Interface<select class="form-control" onchange="updateSelectedControllerSetting('command_interface', this.value)">${interfaceOptions}</select></label>`;
            } else if (type.includes('PidController')) {
                const referenceOptions = ['position', 'velocity', 'acceleration', 'effort'].map(value =>
                    `<option value="${value}" ${settings.reference_and_state_interface === value ? 'selected' : ''}>${value}</option>`
                ).join('');
                specific = `
                    <div class="joint-property-grid two-column" style="margin-top:10px;">
                        <label>Command Interface<select class="form-control" onchange="updateSelectedControllerSetting('command_interface', this.value)">${interfaceOptions}</select></label>
                        <label>Reference / State<select class="form-control" onchange="updateSelectedControllerSetting('reference_and_state_interface', this.value)">${referenceOptions}</select></label>
                    </div>
                    <div class="joint-property-grid three-column">
                        ${['p','i','d'].map(key => `<label>${key.toUpperCase()}<input type="number" step="0.01" class="form-control" value="${Number(settings[key] ?? (key === 'p' ? 1 : 0))}" onchange="updateSelectedControllerSetting('${key}', this.value, true)"></label>`).join('')}
                    </div>`;
            } else if (type.includes('JointStateBroadcaster')) {
                specific = `<div class="info-box" style="margin-top:10px;">이 타입은 관절 상태만 발행합니다. command interface를 점유하거나 모터를 움직이지 않습니다.</div>`;
            }
            return specific;
        }

        function togglePatcherGroupingMode() {
            patcherGroupingMode = !patcherGroupingMode;
            if (!patcherGroupingMode) patcherGroupSelection.clear();
            render({ skipPreview: true });
            const status = document.getElementById('patcher-validation');
            if (status && patcherGroupingMode) {
                status.textContent = '남길 링크와 합칠 링크들을 차례로 선택한 뒤 병합 버튼을 누르세요.';
            }
        }

        function togglePatcherGroupNode(node) {
            if (patcherGroupSelection.has(node)) {
                patcherGroupSelection.delete(node);
            } else {
                patcherGroupSelection.add(node);
            }
            render({ skipPreview: true });
            const target = getPatcherGroupTarget();
            const status = document.getElementById('patcher-validation');
            if (status && patcherGroupSelection.size > 0) {
                status.textContent = `그룹화 선택 ${patcherGroupSelection.size}개 · 병합 후 남을 링크: ${target ? target.name : '-'}`;
            }
        }

        function mergePatcherSelection() {
            if (patcherGroupSelection.size < 2) return;
            const target = getPatcherGroupTarget();
            if (!target) return;
            saveState();
            const sources = [...patcherGroupSelection].filter(node => node !== target);
            sources.forEach(source => mergePatcherNodeInto(source, target, false));
            patcherGroupSelection.clear();
            patcherGroupingMode = false;
            render({ previewDelay: 250 });
        }

        function uniquePatcherLinkName(requestedName, reservedNames) {
            const base = normalizedLinkName(requestedName) || 'part';
            if (!reservedNames.has(base)) {
                reservedNames.add(base);
                return base;
            }
            let suffix = 2;
            while (reservedNames.has(`${base}_${suffix}`)) suffix += 1;
            const uniqueName = `${base}_${suffix}`;
            reservedNames.add(uniqueName);
            return uniqueName;
        }

        function ungroupSelectedPatcherLink() {
            if (!selectedElement || selectedElement.type !== 'link') {
                const status = document.getElementById('patcher-validation');
                if (status) status.textContent = '그룹 해제할 링크 카드를 먼저 선택하세요.';
                return false;
            }
            return ungroupPatcherLink(selectedElement.node);
        }

        function ungroupPatcherLink(node) {
            if (!treeData || !node || (node.components || []).length < 2) {
                const status = document.getElementById('patcher-validation');
                if (status) status.textContent = '두 개 이상의 부품이 들어 있는 링크만 그룹 해제할 수 있습니다.';
                return false;
            }

            saveState();
            const components = node.components.slice();
            const anchorComponent = components.shift();
            const entries = patcherEntries();
            const reservedNames = new Set(entries.map(item => item.node.name));
            const origin = getPatcherPosition(node, entries);
            treeData._patcher_positions = treeData._patcher_positions || {};
            node.components = [anchorComponent];
            node.is_finalized = false;
            node.children = node.children || [];

            components.forEach((component, componentIndex) => {
                const releasedNode = {
                    name: uniquePatcherLinkName(component, reservedNames),
                    components: [component],
                    children: [],
                    is_finalized: false,
                };
                const releasedId = ensurePatcherNodeId(releasedNode);
                const column = componentIndex % 4;
                const row = Math.floor(componentIndex / 4);
                treeData._patcher_positions[releasedId] = {
                    x: origin.x + 42 + column * 210,
                    y: origin.y + 125 + row * 105,
                };
                const storageInfo = patcherRelativeJointInfo(node, releasedNode);
                storageInfo.provenance = 'user_patcher_disconnected';
                node.children.push({
                    joint_name: `disconnected_${releasedNode.name}`,
                    joint_type: 'fixed',
                    joint_info: storageInfo,
                    link_group: releasedNode,
                });
            });

            patcherGroupSelection.delete(node);
            selectedElement = { type: 'link', node, jointObj: null };
            viewerSelectedComponent = null;
            viewerSelectedComponents.clear();
            previewRigDirty = true;
            applyLinkGroupColors();
            render({ previewDelay: 250 });
            const status = document.getElementById('patcher-validation');
            if (status) {
                status.textContent = `그룹 해제 완료 · ${anchorComponent}은 기존 연결을 유지하고, 나머지 ${components.length}개 부품은 미연결 카드로 분리했습니다.`;
                status.classList.remove('ok');
            }
            return true;
        }

        function extractComponentFromPatcherLink(node, component) {
            if (!treeData || !node || !(node.components || []).includes(component)) {
                return false;
            }
            if ((node.components || []).length <= 1) {
                const status = document.getElementById('patcher-validation');
                if (status) status.textContent = '링크에는 최소 한 개의 부품이 남아 있어야 합니다.';
                return false;
            }
            if (!window.confirm(`'${component}' 부품을 '${node.name}' 링크에서 빼낼까요?`)) {
                return false;
            }

            const entries = patcherEntries();
            const affectedJointCount = entries.filter(item => {
                if (!item.jointObj || !item.jointObj.joint_info) return false;
                if (item.parentNode !== node && item.node !== node) return false;
                const info = item.jointObj.joint_info;
                const snapUsesComponent = info._joint_snap
                    && info._joint_snap.component === component;
                const mates = info._joint_mates || {};
                return snapUsesComponent
                    || mates.parent_component === component
                    || mates.child_component === component;
            }).length;

            saveState();
            node.components = node.components.filter(item => item !== component);
            node.children = node.children || [];
            const reservedNames = new Set(entries.map(item => item.node.name));
            const releasedNode = {
                name: uniquePatcherLinkName(component, reservedNames),
                components: [component],
                children: [],
                is_finalized: false,
            };
            const storageInfo = patcherRelativeJointInfo(node, releasedNode);
            storageInfo.provenance = 'user_patcher_disconnected';
            node.children.push({
                joint_name: `disconnected_${releasedNode.name}`,
                joint_type: 'fixed',
                joint_info: storageInfo,
                link_group: releasedNode,
            });

            const origin = getPatcherPosition(node, entries);
            const releasedIndex = node.children.filter(
                child => !isPatcherJointActive(child)
            ).length - 1;
            const column = Math.max(0, releasedIndex) % 3;
            const row = Math.floor(Math.max(0, releasedIndex) / 3);
            treeData._patcher_positions = treeData._patcher_positions || {};
            treeData._patcher_positions[ensurePatcherNodeId(releasedNode)] = {
                x: origin.x + 230 + column * 220,
                y: origin.y + 115 + row * 110,
            };

            patcherGroupSelection.delete(node);
            selectedElement = { type: 'link', node, jointObj: null };
            viewerSelectedComponent = null;
            viewerSelectedComponents.clear();
            previewRigDirty = true;
            applyLinkGroupColors();
            render({ previewDelay: 250 });
            const status = document.getElementById('patcher-validation');
            if (status) {
                status.classList.remove('ok');
                status.textContent = affectedJointCount > 0
                    ? `${component} 분리 완료 · 이 부품을 기준으로 찍은 조인트 ${affectedJointCount}개는 중심·축을 다시 확인하세요.`
                    : `${component} 부품을 ${node.name}에서 빼내 미연결 카드로 만들었습니다.`;
            }
            return true;
        }

        function applyMergedLinkColor(target) {
            if (!target) return;
            const color = getLinkGroupColor(target);
            const material = getLinkGroupMaterial(color);
            (target.components || []).forEach(component => {
                const mesh = meshDict[component];
                if (mesh) {
                    mesh.material = material;
                    mesh.userData.petasosLinkColor = color;
                }
                const edge = meshEdgeDict[component];
                if (edge) {
                    edge.visible = true;
                    edge.material.opacity = 0.48;
                }
            });
            viewerSelectedComponent = null;
            viewerSelectedComponents.clear();
            selectedElement = null;
            applyLinkGroupColors();
        }

        function mergePatcherNodeInto(source, target, saveHistory = true) {
            if (!treeData || !source || !target || source === target) return false;
            const entries = getFlatLinks(treeData, null, -1);
            const sourceEntry = entries.find(item => item.node === source);
            const targetEntry = entries.find(item => item.node === target);
            if (!sourceEntry || !targetEntry) return false;
            if (saveHistory) saveState();

            if (source === treeData) {
                if (!targetEntry.parentList) return false;
                const targetIndex = targetEntry.parentList.findIndex(child => child.link_group === target);
                if (targetIndex >= 0) targetEntry.parentList.splice(targetIndex, 1);

                const metadata = {};
                Object.keys(source).forEach(key => {
                    if (key.startsWith('_') && key !== '_patcher_id') {
                        metadata[key] = source[key];
                        delete source[key];
                    }
                });
                Object.assign(target, metadata);
                target.children = [
                    ...(target.children || []),
                    ...(source.children || []),
                ];
                treeData = target;
                if (treeData._patcher_world_connected) {
                    treeData._patcher_world_root_id = ensurePatcherNodeId(treeData);
                }
            } else if (nodeContainsPatcherNode(source, target)) {
                if (!sourceEntry.parentList || !targetEntry.parentList) return false;
                const targetIndex = targetEntry.parentList.findIndex(child => child.link_group === target);
                if (targetIndex >= 0) targetEntry.parentList.splice(targetIndex, 1);
                const incomingIndex = sourceEntry.parentList.findIndex(child => child.link_group === source);
                if (incomingIndex < 0) return false;
                const incomingJoint = sourceEntry.parentList[incomingIndex];
                incomingJoint.link_group = target;
                if (incomingJoint.joint_info) {
                    incomingJoint.joint_info.child = target.name;
                }
                target.children = [
                    ...(target.children || []),
                    ...(source.children || []),
                ];
            } else {
                if (!sourceEntry.parentList) return false;
                const sourceIndex = sourceEntry.parentList.findIndex(child => child.link_group === source);
                if (sourceIndex < 0) return false;
                sourceEntry.parentList.splice(sourceIndex, 1);
                target.children = [
                    ...(target.children || []),
                    ...(source.children || []),
                ];
            }

            target.components = [...new Set([
                ...(target.components || []),
                ...(source.components || []),
            ])];
            target.is_finalized = true;
            autoRename(target);
            if (treeData._patcher_positions && source._patcher_id) {
                delete treeData._patcher_positions[source._patcher_id];
            }
            previewRigDirty = true;
            applyMergedLinkColor(target);
            selectedElement = { type: 'link', node: target, jointObj: null };
            viewerSelectedComponent = null;
            viewerSelectedComponents.clear();
            if (saveHistory) render({ previewDelay: 250 });
            return true;
        }

        function findPatcherMergeTarget(draggedElement, pointerX = null, pointerY = null) {
            const draggedRect = draggedElement.getBoundingClientRect();
            const draggedArea = Math.max(1, draggedRect.width * draggedRect.height);
            let best = null;
            let bestRatio = 0;
            document.querySelectorAll('.patcher-node:not(.world-node)').forEach(candidate => {
                if (candidate === draggedElement) return;
                const rect = candidate.getBoundingClientRect();
                const width = Math.max(0, Math.min(draggedRect.right, rect.right) - Math.max(draggedRect.left, rect.left));
                const height = Math.max(0, Math.min(draggedRect.bottom, rect.bottom) - Math.max(draggedRect.top, rect.top));
                const overlapArea = width * height;
                const candidateArea = Math.max(1, rect.width * rect.height);
                const ratio = overlapArea / Math.min(draggedArea, candidateArea);
                const pointerInside = Number.isFinite(pointerX) && Number.isFinite(pointerY)
                    && pointerX >= rect.left && pointerX <= rect.right
                    && pointerY >= rect.top && pointerY <= rect.bottom;
                const score = pointerInside ? Math.max(1, ratio) : ratio;
                if ((pointerInside || ratio >= 0.08) && score > bestRatio) {
                    best = candidate;
                    bestRatio = score;
                }
            });
            return best;
        }

        function attachPatcherNodeMove(handle, node, element) {
            handle.onpointerdown = event => {
                if (event.button !== 0) return;
                if (patcherGroupingMode) return;
                event.preventDefault();
                event.stopPropagation();
                const startX = event.clientX;
                const startY = event.clientY;
                const id = ensurePatcherNodeId(node);
                let moving = false;
                let mergeTargetElement = null;
                const start = {
                    x: parseFloat(element.style.left) || 0,
                    y: parseFloat(element.style.top) || 0,
                };
                const move = moveEvent => {
                    if (!moving) {
                        if (Math.hypot(moveEvent.clientX - startX, moveEvent.clientY - startY) < 4) return;
                        moving = true;
                        saveState();
                        element.classList.add('merge-dragging');
                    }
                    const zoom = getPatcherView().zoom;
                    const x = Math.max(8, start.x + (moveEvent.clientX - startX) / zoom);
                    const y = Math.max(8, start.y + (moveEvent.clientY - startY) / zoom);
                    element.style.left = `${x}px`;
                    element.style.top = `${y}px`;
                    treeData._patcher_positions = treeData._patcher_positions || {};
                    treeData._patcher_positions[id] = { x, y };
                    const nextTarget = findPatcherMergeTarget(
                        element,
                        moveEvent.clientX,
                        moveEvent.clientY
                    );
                    if (mergeTargetElement !== nextTarget) {
                        if (mergeTargetElement) mergeTargetElement.classList.remove('merge-drop-target');
                        mergeTargetElement = nextTarget;
                        if (mergeTargetElement) mergeTargetElement.classList.add('merge-drop-target');
                    }
                    const status = document.getElementById('patcher-validation');
                    if (status && mergeTargetElement?._petasosNode) {
                        status.textContent = `놓으면 ${mergeTargetElement._petasosNode.name} 링크에 합쳐집니다.`;
                    }
                    schedulePatcherCableRender();
                };
                const end = endEvent => {
                    document.removeEventListener('pointermove', move);
                    document.removeEventListener('pointerup', end);
                    document.removeEventListener('pointercancel', end);
                    element.classList.remove('merge-dragging');
                    if (moving && endEvent && endEvent.type !== 'pointercancel') {
                        const finalTarget = findPatcherMergeTarget(
                            element,
                            endEvent.clientX,
                            endEvent.clientY
                        );
                        if (finalTarget) mergeTargetElement = finalTarget;
                    }
                    if (mergeTargetElement) {
                        mergeTargetElement.classList.remove('merge-drop-target');
                        const targetNode = mergeTargetElement._petasosNode;
                        mergeTargetElement = null;
                        if (moving && targetNode && mergePatcherNodeInto(node, targetNode, false)) {
                            render({ previewDelay: 250 });
                            return;
                        }
                    }
                    if (moving) {
                        updatePatcherAssistantButtonStates();
                        validatePatcherGraph(true);
                    }
                };
                document.addEventListener('pointermove', move);
                document.addEventListener('pointerup', end);
                document.addEventListener('pointercancel', end);
            };
        }

        function patcherNodeIdFor(node) {
            return node === '__world__' ? '__world__' : ensurePatcherNodeId(node);
        }

        function patcherPortPoint(canvas, nodeId, portClass, outputKey = null) {
            const ports = Array.from(canvas.querySelectorAll(
                `.patcher-node[data-patcher-id="${nodeId}"] .patcher-port.${portClass}`
            ));
            const port = outputKey === null
                ? ports[0]
                : ports.find(candidate => candidate.dataset.outputKey === outputKey);
            if (!port) return null;
            const canvasRect = canvas.getBoundingClientRect();
            const rect = port.getBoundingClientRect();
            const scale = canvas.offsetWidth ? canvasRect.width / canvas.offsetWidth : 1;
            return {
                x: (rect.left - canvasRect.left + rect.width / 2) / scale,
                y: (rect.top - canvasRect.top + rect.height / 2) / scale,
            };
        }

        function cablePath(start, end) {
            const bend = Math.max(80, Math.abs(end.x - start.x) * 0.48);
            return `M ${start.x} ${start.y} C ${start.x + bend} ${start.y}, ${end.x - bend} ${end.y}, ${end.x} ${end.y}`;
        }

        function schedulePatcherCableRender() {
            if (patcherCableFrame) cancelAnimationFrame(patcherCableFrame);
            patcherCableFrame = requestAnimationFrame(() => {
                patcherCableFrame = null;
                renderPatcherCables();
            });
        }

        function renderPatcherControllerFrames(canvas, entries) {
            canvas.querySelectorAll('.patcher-controller-frame').forEach(frame => frame.remove());
            const canvasRect = canvas.getBoundingClientRect();
            const scale = canvas.offsetWidth ? canvasRect.width / canvas.offsetWidth : 1;
            if (!Number.isFinite(scale) || scale <= 0) return;
            const controllerFrameRecords = [];
            robotControllers().forEach(controller => {
                const jointNames = new Set(controller.joints || []);
                const elements = [];
                canvas.querySelectorAll('.patcher-joint-label').forEach(label => {
                    if (jointNames.has(label.dataset.jointName)) elements.push(label);
                });
                entries.forEach(entry => {
                    if (!entry.jointObj || !jointNames.has(entry.jointObj.joint_name)) return;
                    const node = canvas.querySelector(
                        `.patcher-node[data-patcher-id="${ensurePatcherNodeId(entry.node)}"]`
                    );
                    if (node) elements.push(node);
                });
                if (!elements.length) return;
                const rects = elements.map(element => element.getBoundingClientRect());
                // Keep the original generous controller enclosure. Label
                // collisions are handled independently below.
                const padding = 20;
                const left = Math.min(...rects.map(rect => rect.left));
                const top = Math.min(...rects.map(rect => rect.top));
                const right = Math.max(...rects.map(rect => rect.right));
                const bottom = Math.max(...rects.map(rect => rect.bottom));
                const frame = document.createElement('div');
                frame.className = 'patcher-controller-frame';
                const color = controller.color || CONTROLLER_PALETTE[0];
                frame.style.setProperty('--controller-color', color);
                frame.style.setProperty('--controller-fill', controllerColorRgba(color, 0.14));
                frame.style.setProperty('--controller-glow', controllerColorRgba(color, 0.3));
                frame.style.setProperty('--controller-label', controllerColorRgba(color, 0.48));
                const isSelected = selectedElement?.type === 'controller'
                    && (selectedElement.controller === controller || selectedElement.controller?.name === controller.name);
                if (isSelected) {
                    frame.classList.add('selected');
                }
                const frameLeft = (left - canvasRect.left) / scale - padding;
                const frameTop = (top - canvasRect.top) / scale - padding;
                const frameWidth = (right - left) / scale + padding * 2;
                const frameHeight = (bottom - top) / scale + padding * 2;
                const frameBounds = {
                    left: frameLeft,
                    top: frameTop,
                    right: frameLeft + frameWidth,
                    bottom: frameTop + frameHeight,
                };
                const topLabelBounds = {
                    left: frameLeft + 12,
                    top: frameTop - 13,
                    right: frameLeft + Math.min(frameWidth, 232),
                    bottom: frameTop + 11,
                };
                frame.style.left = `${frameLeft}px`;
                frame.style.top = `${frameTop}px`;
                frame.style.width = `${frameWidth}px`;
                frame.style.height = `${frameHeight}px`;

                const borderSvg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
                borderSvg.setAttribute('class', 'patcher-controller-border-hit');
                borderSvg.style.position = 'absolute';
                borderSvg.style.inset = '-6px';
                borderSvg.style.width = 'calc(100% + 12px)';
                borderSvg.style.height = 'calc(100% + 12px)';
                borderSvg.style.pointerEvents = 'none';
                borderSvg.style.overflow = 'visible';

                const borderRect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                borderRect.setAttribute('x', '6');
                borderRect.setAttribute('y', '6');
                borderRect.setAttribute('width', String(Math.max(0, frameWidth)));
                borderRect.setAttribute('height', String(Math.max(0, frameHeight)));
                borderRect.setAttribute('rx', '14');
                borderRect.setAttribute('ry', '14');
                borderRect.setAttribute('fill', 'none');
                borderRect.setAttribute('stroke', 'rgba(0,0,0,0.001)');
                borderRect.setAttribute('stroke-width', '16');
                borderRect.style.pointerEvents = 'stroke';
                borderRect.style.cursor = 'pointer';
                borderRect.setAttribute('title', '눌러서 컨트롤러 속성과 이름을 수정');
                borderRect.onpointerdown = event => {
                    event.stopPropagation();
                };
                borderRect.onclick = event => {
                    selectRobotController(event, controller);
                };
                borderSvg.appendChild(borderRect);
                frame.appendChild(borderSvg);

                const label = document.createElement('button');
                label.type = 'button';
                label.className = 'patcher-controller-label' + (isSelected ? ' selected' : '');
                label.textContent = `${controller.name || 'controller'} · ${jointNames.size} joints`;
                label.title = '눌러서 컨트롤러 속성과 이름을 수정';
                label.onpointerdown = event => {
                    event.stopPropagation();
                };
                label.onclick = event => {
                    selectRobotController(event, controller);
                };
                frame.appendChild(label);
                canvas.appendChild(frame);
                controllerFrameRecords.push({ frame, frameBounds, topLabelBounds });
            });
            controllerFrameRecords.forEach((record, index) => {
                const topLabelTouchesAnotherFrame = controllerFrameRecords.some((other, otherIndex) =>
                    otherIndex !== index
                    && record.topLabelBounds.left < other.frameBounds.right
                    && record.topLabelBounds.right > other.frameBounds.left
                    && record.topLabelBounds.top < other.frameBounds.bottom
                    && record.topLabelBounds.bottom > other.frameBounds.top
                );
                record.frame.classList.toggle('label-bottom', topLabelTouchesAnotherFrame);
            });
        }

        function renderPatcherCables() {
            const canvas = document.getElementById('patcher-canvas');
            if (!canvas) return;
            const svg = canvas.querySelector('.patcher-cables');
            if (!svg) return;
            svg.innerHTML = `
                <defs>
                    <marker id="patcher-arrow-fixed" viewBox="0 0 10 10" refX="8" refY="5"
                            markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                        <path d="M 0 0 L 10 5 L 0 10 z" fill="#ffd22e"></path>
                    </marker>
                    <marker id="patcher-arrow-motion" viewBox="0 0 10 10" refX="8" refY="5"
                            markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                        <path d="M 0 0 L 10 5 L 0 10 z" fill="#40e1c1"></path>
                    </marker>
                    <marker id="patcher-arrow-prismatic" viewBox="0 0 10 10" refX="8" refY="5"
                            markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                        <path d="M 0 0 L 10 5 L 0 10 z" fill="#48a9ff"></path>
                    </marker>
                    <marker id="patcher-arrow-disabled" viewBox="0 0 10 10" refX="8" refY="5"
                            markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                        <path d="M 0 0 L 10 5 L 0 10 z" fill="#66707a"></path>
                    </marker>
                </defs>`;
            canvas.querySelectorAll('.patcher-joint-label, .patcher-controller-frame').forEach(element => element.remove());
            const entries = patcherEntries();

            const addCable = (start, end, jointObj, className = '') => {
                if (!start || !end) return;
                const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                path.setAttribute('d', cablePath(start, end));
                path.classList.add('patcher-cable');
                const cableDisabled = jointObj && (isJointDisabled(jointObj) || (jointObj.link_group && isLinkDisabled(jointObj.link_group)));
                if (className) path.classList.add(className);
                if (cableDisabled) path.classList.add('disabled');
                const markerType = cableDisabled
                    ? 'disabled'
                    : (className === 'prismatic'
                        ? 'prismatic'
                        : (className === 'world' || className === 'revolute' || className === 'continuous' ? 'motion' : 'fixed'));
                path.setAttribute('marker-end', `url(#patcher-arrow-${markerType})`);
                if (jointObj && selectedElement && selectedElement.type === 'joint' && selectedElement.jointObj === jointObj) {
                    path.classList.add('selected');
                }
                svg.appendChild(path);
                if (!jointObj) return;
                const label = document.createElement('button');
                label.type = 'button';
                label.className = 'patcher-joint-label';
                label.dataset.jointName = jointObj.joint_name;
                if (cableDisabled) {
                    label.classList.add('disabled');
                }
                if (selectedElement && selectedElement.type === 'joint' && selectedElement.jointObj === jointObj) {
                    label.classList.add('selected');
                }
                if (patcherControllerJointSelection.has(jointObj)) {
                    label.classList.add('controller-pick');
                }
                label.style.left = `${(start.x + end.x) / 2}px`;
                label.style.top = `${(start.y + end.y) / 2}px`;
                label.textContent = cableDisabled
                    ? `${jointObj.joint_name} · ${jointObj.joint_type} (비활성)`
                    : `${jointObj.joint_name} · ${jointObj.joint_type}`;
                const childEntry = entries.find(item => item.jointObj === jointObj);
                label.onclick = event => {
                    event.stopPropagation();
                    if (patcherControllerSelectionMode) {
                        toggleControllerJointSelection(jointObj);
                        return;
                    }
                    if (childEntry) selectElement('joint', childEntry.node, jointObj);
                };
                canvas.appendChild(label);
            };

            if (rootJointMode() !== 'none' && treeData._patcher_world_connected) {
                addCable(
                    patcherPortPoint(canvas, '__world__', 'output'),
                    patcherPortPoint(canvas, ensurePatcherNodeId(treeData), 'input'),
                    null,
                    'world'
                );
            }

            entries.slice(1).forEach(item => {
                if (!isPatcherJointActive(item.jointObj) || !item.parentNode) return;
                addCable(
                    patcherPortPoint(
                        canvas,
                        ensurePatcherNodeId(item.parentNode),
                        'output',
                        ensurePatcherNodeId(item.node)
                    ),
                    patcherPortPoint(canvas, ensurePatcherNodeId(item.node), 'input'),
                    item.jointObj,
                    item.jointObj.joint_type || 'fixed'
                );
            });

            renderPatcherControllerFrames(canvas, entries);

            if (patcherConnectionDrag && patcherConnectionDrag.pointer) {
                const start = patcherPortPoint(
                    canvas,
                    patcherNodeIdFor(patcherConnectionDrag.parentNode),
                    'output',
                    patcherConnectionDrag.outputKey || null
                );
                if (start) {
                    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                    path.setAttribute('d', cablePath(start, patcherConnectionDrag.pointer));
                    path.classList.add('patcher-temp-cable');
                    svg.appendChild(path);
                }
            }
        }

        function armPatcherConnectionByClick(event, parentNode, outputKey = null) {
            if (patcherConnectionDrag) return;
            event.preventDefault();
            event.stopPropagation();
            const canvas = document.getElementById('patcher-canvas');
            const start = canvas && patcherPortPoint(
                canvas,
                patcherNodeIdFor(parentNode),
                'output',
                outputKey
            );
            if (!canvas || !start) return;
            patcherConnectionDrag = {
                parentNode,
                outputKey,
                pointer: { x: start.x + 90, y: start.y },
            };
            canvas.querySelectorAll('.patcher-port.input').forEach(
                port => port.classList.add('connect-target')
            );
            const status = document.getElementById('patcher-validation');
            if (status) {
                status.textContent = parentNode === '__world__'
                    ? 'WORLD에 연결할 루트 링크의 입력 포트를 클릭하세요.'
                    : '연결할 자식 링크의 왼쪽 입력 포트를 클릭하세요.';
            }
            schedulePatcherCableRender();
        }

        function beginPatcherConnection(event, parentNode, outputKey = null) {
            event.preventDefault();
            event.stopPropagation();
            const canvas = document.getElementById('patcher-canvas');
            if (!canvas) return;
            if (patcherConnectionDrag) cancelPatcherConnection();
            const rect = canvas.getBoundingClientRect();
            const scale = canvas.offsetWidth ? rect.width / canvas.offsetWidth : 1;
            patcherConnectionDrag = {
                parentNode,
                outputKey,
                pointer: { x: (event.clientX - rect.left) / scale, y: (event.clientY - rect.top) / scale },
            };
            canvas.querySelectorAll('.patcher-port.input').forEach(port => port.classList.add('connect-target'));
            const move = moveEvent => {
                if (!patcherConnectionDrag) return;
                patcherConnectionDrag.pointer = {
                    x: (moveEvent.clientX - rect.left) / scale,
                    y: (moveEvent.clientY - rect.top) / scale,
                };
                schedulePatcherCableRender();
            };
            const end = () => {
                document.removeEventListener('pointermove', move);
                document.removeEventListener('pointerup', end);
                if (patcherConnectionDrag) {
                    const status = document.getElementById('patcher-validation');
                    if (status) {
                        status.textContent = parentNode === '__world__'
                            ? 'WORLD에 연결할 루트 링크의 입력 포트를 클릭하세요.'
                            : '연결할 자식 링크의 왼쪽 입력 포트를 클릭하세요.';
                    }
                }
            };
            document.addEventListener('pointermove', move);
            document.addEventListener('pointerup', end);
            schedulePatcherCableRender();
        }

        function cancelPatcherConnection() {
            patcherConnectionDrag = null;
            document.querySelectorAll('.patcher-port.connect-target, .tree-wire-port.connect-target').forEach(
                port => port.classList.remove('connect-target')
            );
            if (TREE_EDITOR_MODE) scheduleTreeWireRender();
            else schedulePatcherCableRender();
        }

        function nodeContainsPatcherNode(rootNode, targetNode) {
            if (rootNode === targetNode) return true;
            return (rootNode.children || []).some(
                child => nodeContainsPatcherNode(child.link_group, targetNode)
            );
        }

        function nextPatcherJointName() {
            const used = new Set(
                patcherEntries()
                    .filter(item => isPatcherJointActive(item.jointObj))
                    .map(item => item.jointObj.joint_name)
            );
            let index = 1;
            while (used.has(`joint_${index}`)) index += 1;
            return `joint_${index}`;
        }

        function finalizeConnectedPatcherNode(node) {
            if (!node || node.is_finalized) return false;
            node.is_finalized = true;
            autoRename(node);
            return true;
        }

        function syncPatcherJointLinkNames() {
            getFlatLinks(treeData, null, -1).forEach(item => {
                if (!item.jointObj || !item.jointObj.joint_info) return;
                if (item.parentNode) {
                    item.jointObj.joint_info.parent = item.parentNode.name;
                }
                item.jointObj.joint_info.child = item.node.name;
            });
        }

        function patcherRelativeJointInfo(parentNode, childNode) {
            const parentComponent = (parentNode.components || [])[0];
            const childComponent = (childNode.components || [])[0];
            const transforms = treeData._preview_transforms || {};
            const parentRaw = transforms[parentComponent];
            const childRaw = transforms[childComponent];
            let xyz = [0, 0, 0];
            let rpy = [0, 0, 0];
            if (Array.isArray(parentRaw) && parentRaw.length === 16 && Array.isArray(childRaw) && childRaw.length === 16) {
                const parentMatrix = new THREE.Matrix4().fromArray(parentRaw);
                const childMatrix = new THREE.Matrix4().fromArray(childRaw);
                const relative = parentMatrix.clone().invert().multiply(childMatrix);
                const position = new THREE.Vector3();
                const quaternion = new THREE.Quaternion();
                const scale = new THREE.Vector3();
                relative.decompose(position, quaternion, scale);
                const unitsPerMeter = Number(treeData._preview_units_per_meter) || 1000.0;
                xyz = position.divideScalar(unitsPerMeter).toArray();
                const euler = new THREE.Euler().setFromQuaternion(quaternion, 'ZYX');
                rpy = [euler.x, euler.y, euler.z];
            }
            return {
                parent: parentNode.name,
                child: childNode.name,
                type: 'fixed',
                xyz,
                rpy,
                _manual_rpy: rpy.slice(),
                axis: [0, 0, 1],
                lower_limit: 0,
                upper_limit: 0,
                provenance: 'user_patcher',
            };
        }

        function setPatcherWorldRoot(node) {
            if (!treeData || !node) return;
            saveState();
            if (node !== treeData) {
                const oldRoot = treeData;
                const entry = getFlatLinks(oldRoot, null, -1).find(item => item.node === node);
                if (!entry || !entry.parentList) return;
                const index = entry.parentList.findIndex(child => child.link_group === node);
                if (index >= 0) entry.parentList.splice(index, 1);

                const storageInfo = patcherRelativeJointInfo(node, oldRoot);
                const metadata = {};
                Object.keys(oldRoot).forEach(key => {
                    if (key.startsWith('_') && key !== '_patcher_id') {
                        metadata[key] = oldRoot[key];
                        delete oldRoot[key];
                    }
                });
                Object.assign(node, metadata);
                node.children = node.children || [];
                storageInfo.provenance = 'user_patcher_disconnected';
                node.children.push({
                    joint_name: `disconnected_${oldRoot.name}`,
                    joint_type: 'fixed',
                    joint_info: storageInfo,
                    link_group: oldRoot,
                });
                treeData = node;
            }
            finalizeConnectedPatcherNode(treeData);
            syncPatcherJointLinkNames();
            applyLinkGroupColors();
            treeData._patcher_world_connected = true;
            treeData._patcher_world_root_id = ensurePatcherNodeId(treeData);
            selectedElement = { type: 'link', node: treeData, jointObj: null };
            previewRigDirty = true;
            render({ previewDelay: 250 });
        }

        function finishPatcherConnection(event, childNode) {
            event.preventDefault();
            event.stopPropagation();
            if (!patcherConnectionDrag) return;
            const parentNode = patcherConnectionDrag.parentNode;
            if (parentNode === '__world__') {
                cancelPatcherConnection();
                setPatcherWorldRoot(childNode);
                return;
            }
            if (parentNode === childNode || childNode === treeData || nodeContainsPatcherNode(childNode, parentNode)) {
                const status = document.getElementById('patcher-validation');
                if (status) status.textContent = '이 연결은 순환 구조를 만들기 때문에 사용할 수 없습니다.';
                cancelPatcherConnection();
                return;
            }
            const entries = patcherEntries();
            const childEntry = entries.find(item => item.node === childNode);
            if (!childEntry || !childEntry.parentList) {
                cancelPatcherConnection();
                return;
            }
            saveState();
            // A loose CAD part becomes a proper URDF link as soon as it is
            // used as either endpoint of an explicit joint connection.
            finalizeConnectedPatcherNode(parentNode);
            finalizeConnectedPatcherNode(childNode);
            const oldIndex = childEntry.parentList.findIndex(child => child.link_group === childNode);
            if (oldIndex >= 0) childEntry.parentList.splice(oldIndex, 1);
            parentNode.children = parentNode.children || [];
            const joint = {
                joint_name: nextPatcherJointName(),
                joint_type: 'fixed',
                joint_info: patcherRelativeJointInfo(parentNode, childNode),
                link_group: childNode,
            };
            parentNode.children.push(joint);
            syncPatcherJointLinkNames();
            applyLinkGroupColors();
            selectedElement = { type: 'joint', node: childNode, jointObj: joint };
            previewRigDirty = true;
            cancelPatcherConnection();
            render({ previewDelay: 250 });
        }

        function disconnectPatcherPort(event, node, jointObj = null) {
            if (event) {
                event.preventDefault();
                event.stopPropagation();
            }
            cancelPatcherConnection();
            if (jointObj && isPatcherJointActive(jointObj)) {
                saveState();
                jointObj.joint_info = jointObj.joint_info || {};
                jointObj.joint_info.provenance = 'user_patcher_disconnected';
                selectedElement = { type: 'link', node, jointObj: null };
                previewRigDirty = true;
                render();
                return;
            }
            if (node === treeData && treeData._patcher_world_connected) {
                saveState();
                treeData._patcher_world_connected = false;
                selectedElement = { type: 'link', node: treeData, jointObj: null };
                previewRigDirty = true;
                render();
            }
        }

        function disconnectSelectedJoint() {
            if (!selectedElement || selectedElement.type !== 'joint' || !selectedElement.jointObj) {
                const status = document.getElementById('patcher-validation');
                if (status) status.textContent = '끊을 조인트 선을 먼저 클릭하세요.';
                return;
            }
            saveState();
            const joint = selectedElement.jointObj;
            joint.joint_info = joint.joint_info || {};
            joint.joint_info.provenance = 'user_patcher_disconnected';
            selectedElement = { type: 'link', node: selectedElement.node, jointObj: null };
            previewRigDirty = true;
            render();
        }

        function createNodeElement(node, parentList, index, jointObj) {
            const li = document.createElement('li');
            const wrapper = document.createElement('div');
            wrapper.className = 'node-wrapper';
            const disabled = isLinkDisabled(node);

            if (jointObj) {
                const jBadge = document.createElement('div');
                jBadge.className = 'joint-badge selectable';
                const groupCandidate = isPatcherGroupCandidate(jointObj);
                if (groupCandidate) jBadge.classList.add('group-candidate');
                if (selectedElement && selectedElement.type === 'joint' && selectedElement.jointObj === jointObj) {
                    jBadge.classList.add('selected');
                }
                const jointDisabled = isJointDisabled(jointObj);
                if (jointDisabled) jBadge.classList.add('disabled');
                jBadge.innerHTML = groupCandidate
                    ? `🧲 묶음 후보 · 겹쳐서 링크 만들기`
                    : `⚙️ ${jointObj.joint_name} (${jointObj.joint_type})${jointDisabled ? ' <span style="font-size:10px;opacity:0.8;">(비활성)</span>' : ''}`;
                jBadge.title = groupCandidate
                    ? '함께 움직이는 부품이면 카드를 겹쳐 병합하고, 링크 사이 연결이면 클릭해 실제 조인트로 전환하세요.'
                    : `${jointObj.joint_name} (${jointObj.joint_type})${jointDisabled ? ' [비활성화됨]' : ''}`;
                jBadge.onclick = (e) => {
                    e.stopPropagation();
                    selectElement('joint', node, jointObj);
                };
                wrapper.appendChild(jBadge);
            }

            const box = document.createElement('div');
            box.className = 'link-box selectable';
            box._petasosNode = node;
            const treeNodeId = ensurePatcherNodeId(node);
            box.dataset.treeNodeId = treeNodeId;
            if (node.is_finalized) box.classList.add('finalized');
            if (disabled) box.classList.add('disabled');
            box.draggable = true;
            
            if (selectedElement && selectedElement.type === 'link' && selectedElement.node === node) {
                box.classList.add('selected');
            }

            const nameDiv = document.createElement('div');
            nameDiv.className = 'link-name';
            nameDiv.style.display = 'flex';
            nameDiv.style.alignItems = 'center';
            nameDiv.style.gap = '6px';
            const treeColorDot = document.createElement('span');
            treeColorDot.className = 'link-color-dot';
            treeColorDot.style.background = colorToCss(getLinkGroupColor(node));
            const treeNameText = document.createElement('span');
            treeNameText.innerText = node.name;
            nameDiv.appendChild(treeColorDot);
            nameDiv.appendChild(treeNameText);

            if (disabled) {
                const disabledBadge = document.createElement('span');
                disabledBadge.className = 'patcher-disabled-badge';
                disabledBadge.style.fontSize = '10px';
                disabledBadge.style.padding = '1px 5px';
                disabledBadge.style.borderRadius = '999px';
                disabledBadge.style.background = 'rgba(239, 68, 68, 0.2)';
                disabledBadge.style.color = '#f87171';
                disabledBadge.style.border = '1px solid rgba(239, 68, 68, 0.4)';
                disabledBadge.innerText = '비활성';
                nameDiv.appendChild(disabledBadge);
            }

            if (node !== treeData) {
                const toggleActiveButton = document.createElement('button');
                toggleActiveButton.type = 'button';
                toggleActiveButton.className = 'patcher-node-toggle';
                toggleActiveButton.style.marginLeft = 'auto';
                updateToggleActiveButtonUi(toggleActiveButton, disabled, node.name);
                toggleActiveButton.onpointerdown = event => event.stopPropagation();
                toggleActiveButton.onclick = event => {
                    event.preventDefault();
                    event.stopPropagation();
                    toggleLinkActive(node);
                };
                nameDiv.appendChild(toggleActiveButton);
            }

            box.appendChild(nameDiv);

            const partsDiv = document.createElement('div');
            partsDiv.className = 'link-parts';
            partsDiv.innerHTML = `<span>${node.components.length} Parts</span><span class="expand-icon">▼</span>`;
            
            const partsList = document.createElement('div');
            partsList.className = 'link-parts-list';
            populateLinkPartsList(partsList, node);
            
            partsDiv.onclick = (e) => {
                e.stopPropagation(); // 부모 선택 이벤트 방지
                box.classList.toggle('expanded');
            };
            
            box.appendChild(partsDiv);
            box.appendChild(partsList);

            const inputPort = document.createElement('button');
            inputPort.type = 'button';
            inputPort.className = 'tree-wire-port input';
            inputPort.dataset.treeNodeId = treeNodeId;
            inputPort.setAttribute('aria-label', `${node.name} 입력 포트`);
            inputPort.title = '부모 링크의 출력 포트를 먼저 누른 뒤 이 입력 포트를 누르세요.';
            inputPort.onpointerup = event => finishTreeConnection(event, node);
            inputPort.onclick = event => finishTreeConnection(event, node);

            const outputPort = document.createElement('button');
            outputPort.type = 'button';
            outputPort.className = 'tree-wire-port output';
            outputPort.dataset.treeNodeId = treeNodeId;
            outputPort.setAttribute('aria-label', `${node.name} 출력 포트`);
            outputPort.title = '이 링크에서 자식 링크로 조인트 연결을 시작합니다.';
            outputPort.onpointerdown = event => {
                if (event.button !== 0) return;
                armTreeConnection(event, node);
            };
            outputPort.onclick = event => {
                event.preventDefault();
                event.stopPropagation();
            };

            box.append(inputPort, outputPort);
            
            box.onclick = (e) => {
                e.stopPropagation();
                selectElement('link', node, null);
            };

            attachDragDropEvents(box, node, parentList, index);

            wrapper.appendChild(box);
            li.appendChild(wrapper);

            if (node.children && node.children.length > 0) {
                const childUl = document.createElement('ul');
                const fixedChildren = node.children.filter(
                    child => (child.joint_type || 'fixed') === 'fixed'
                ).length;
                const useCompactLayout = node.children.length > 6
                    && fixedChildren / node.children.length >= 0.65;
                if (useCompactLayout) {
                    childUl.classList.add('compact-children');
                    const summary = document.createElement('div');
                    summary.className = 'compact-child-summary';
                    summary.innerText = `루트에 연결된 고정 링크 ${fixedChildren}개 · 압축 배치`;
                    li.appendChild(summary);
                }
                node.children.forEach((child, i) => {
                    childUl.appendChild(createNodeElement(child.link_group, node.children, i, child));
                });
                li.appendChild(childUl);
            }

            return li;
        }

        function getFlatLinks(node, parentList, index, parentName = null, jointObj = null, depth = 0, result = [], parentNode = null) {
            result.push({ node, parentList, index, parentName, jointObj, depth, parentNode });
            if (node.children) {
                node.children.forEach((child, i) => {
                    getFlatLinks(child.link_group, node.children, i, node.name, child, depth + 1, result, node);
                });
            }
            return result;
        }

        function renderGroupingList() {
            const listContainer = document.getElementById('grouping-list');
            listContainer.innerHTML = '';
            
            const flatLinks = getFlatLinks(treeData, null, -1);
            document.getElementById('link-count-badge').innerText = `총 ${flatLinks.length}개 링크`;

            flatLinks.forEach(item => {
                const { node, parentList, index, parentName, jointObj, depth } = item;
                const disabled = isLinkDisabled(node);
                
                const itemDiv = document.createElement('div');
                itemDiv.className = 'list-link-item selectable';
                if (node.is_finalized) itemDiv.classList.add('finalized');
                if (disabled) itemDiv.classList.add('disabled');
                itemDiv.draggable = true;
                
                const visualDepth = isPatcherJointActive(jointObj) ? depth : 0;
                itemDiv.style.marginLeft = (visualDepth * 20) + 'px';
                if(visualDepth > 0) {
                    itemDiv.style.borderLeft = '2px dashed #888';
                }
                
                if (selectedElement && selectedElement.type === 'link' && selectedElement.node === node) {
                    itemDiv.classList.add('selected');
                }
                
                let connHtml = '';
                if(parentName && isPatcherJointActive(jointObj)) {
                    let jType = jointObj.joint_type;
                    let typeStyle = isJointDisabled(jointObj) ? 'color:#888;' : (jType === 'fixed' ? 'color:#ff9800;' : 'color:#4caf50;');
                    let jTypeText = isJointDisabled(jointObj) ? `${jType} (비활성)` : jType;
                    connHtml = `<div style="font-size:10px; color:#aaa; margin-bottom:4px;">
                        ↳ <b>${parentName}</b> 와(과) 연결됨 (<span style="${typeStyle}">${jTypeText}</span>: ${jointObj.joint_name})
                    </div>`;
                }

                const titleDiv = document.createElement('div');
                titleDiv.className = 'list-link-title';
                
                const leftDiv = document.createElement('div');
                leftDiv.className = 'list-link-title-left';
                
                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.className = 'cb-finalize';
                cb.checked = node.is_finalized || false;
                cb.onclick = (e) => {
                    e.stopPropagation();
                    saveState();
                    node.is_finalized = e.target.checked;
                    if (node.is_finalized) autoRename(node);
                    render();
                };
                
                const nameSpan = document.createElement('span');
                nameSpan.style.display = 'inline-flex';
                nameSpan.style.alignItems = 'center';
                nameSpan.style.gap = '6px';
                const listColorDot = document.createElement('span');
                listColorDot.className = 'link-color-dot';
                listColorDot.style.background = colorToCss(getLinkGroupColor(node));
                const listNameText = document.createElement('span');
                listNameText.innerText = node.name;
                nameSpan.appendChild(listColorDot);
                nameSpan.appendChild(listNameText);
                
                leftDiv.appendChild(cb);
                leftDiv.appendChild(nameSpan);
                
                const badgeSpan = document.createElement('span');
                badgeSpan.className = 'list-link-badge';
                badgeSpan.innerText = disabled ? `${node.components.length} Parts (비활성)` : `${node.components.length} Parts`;
                if (disabled) badgeSpan.style.color = '#ff7b7b';
                
                titleDiv.appendChild(leftDiv);
                if (node !== treeData) {
                    const listToggle = document.createElement('button');
                    listToggle.type = 'button';
                    listToggle.className = 'patcher-node-toggle';
                    listToggle.style.marginLeft = 'auto';
                    listToggle.style.marginRight = '6px';
                    updateToggleActiveButtonUi(listToggle, disabled, node.name);
                    listToggle.onclick = e => {
                        e.stopPropagation();
                        toggleLinkActive(node);
                    };
                    titleDiv.appendChild(listToggle);
                }
                titleDiv.appendChild(badgeSpan);
                
                const partsDiv = document.createElement('div');
                partsDiv.className = 'list-link-parts';
                partsDiv.innerText = node.components.join(', ');

                if (connHtml) itemDiv.innerHTML = connHtml;
                itemDiv.appendChild(titleDiv);
                itemDiv.appendChild(partsDiv);

                itemDiv.onclick = (e) => {
                    e.stopPropagation();
                    selectElement('link', node, null);
                };

                attachDragDropEvents(itemDiv, node, parentList, index);
                listContainer.appendChild(itemDiv);
            });
        }

        function attachDragDropEvents(domElement, node, parentList, index) {
            domElement.ondragstart = (e) => {
                e.stopPropagation();
                draggedPhysicalMaterialKey = null;
                document.body.classList.add('is-dragging');
                if (previewUpdateTimer) {
                    clearTimeout(previewUpdateTimer);
                    previewUpdateTimer = null;
                }
                draggedNode = node;
                draggedNodeParentList = parentList;
                draggedNodeIndex = index;
                e.dataTransfer.effectAllowed = 'move';
                setTimeout(() => domElement.style.opacity = '0.4', 0);
            };
            domElement.ondragend = () => {
                document.body.classList.remove('is-dragging');
                if (currentDragOverElement) {
                    currentDragOverElement.classList.remove('drag-over');
                    currentDragOverElement = null;
                }
                domElement.style.opacity = '1';
            };
            domElement.ondragover = (e) => {
                e.preventDefault(); e.stopPropagation();
                if (draggedPhysicalMaterialKey) {
                    e.dataTransfer.dropEffect = 'copy';
                    if (currentDragOverElement && currentDragOverElement !== domElement) {
                        currentDragOverElement.classList.remove('drag-over', 'material-drop-target');
                    }
                    currentDragOverElement = domElement;
                    domElement.classList.add('material-drop-target');
                    return;
                }
                if (draggedNode && draggedNode !== node && currentDragOverElement !== domElement) {
                    if (currentDragOverElement) currentDragOverElement.classList.remove('drag-over');
                    currentDragOverElement = domElement;
                    domElement.classList.add('drag-over');
                }
            };
            domElement.ondragleave = (e) => { 
                e.preventDefault(); e.stopPropagation();
                if (currentDragOverElement === domElement) {
                    domElement.classList.remove('drag-over', 'material-drop-target');
                    currentDragOverElement = null;
                }
            };
            domElement.ondrop = (e) => {
                e.preventDefault(); e.stopPropagation();
                document.body.classList.remove('is-dragging');
                if (currentDragOverElement) {
                    currentDragOverElement.classList.remove('drag-over', 'material-drop-target');
                    currentDragOverElement = null;
                }
                const materialKey = draggedPhysicalMaterialKey || e.dataTransfer.getData('application/x-petasos-material');
                if (materialKey) {
                    applyPhysicalMaterialToLink(node, materialKey);
                    finishPhysicalMaterialDrag();
                    return;
                }
                
                if (draggedNode && draggedNode !== node) {
                    saveState(); // 드래그 앤 드롭 전 상태 저장
                    const merged = mergePatcherNodeInto(draggedNode, node, false);
                    if (merged) {
                        node.is_finalized = true;
                        autoRename(node);
                        selectedElement = { type: 'link', node, jointObj: null };
                        viewerSelectedComponent = null;
                        viewerSelectedComponents.clear();
                        previewRigDirty = true;
                        render({ previewDelay: 900 });
                        highlight3DComponents(node.components);
                    }
                    draggedNode = null;
                    draggedNodeParentList = null;
                    draggedNodeIndex = -1;
                }
            };
        }

        function selectElement(type, node, jointObj) {
            if (jointOriginPickMode && jointOriginPickJoint !== jointObj) {
                cancelJointOriginPick('다른 항목을 선택하여 조인트 위치 지정을 취소했습니다.');
            }
            baseFootprintFrameSelected = false;
            if (baseFootprintFrameMarker) baseFootprintFrameMarker.visible = false;
            viewerSelectedComponent = null;
            viewerSelectedComponents.clear();
            // 이미 선택된 항목을 다시 클릭하면 선택 해제 (토글 기능)
            if (selectedElement && selectedElement.type === type && selectedElement.node === node && selectedElement.jointObj === jointObj) {
                clearSelection();
            } else {
                selectedElement = { type, node, jointObj };

                // 3D 뷰어 하이라이트 동기화
                if (type === 'link') {
                    highlight3DComponents(node.components);
                } else if (type === 'joint') {
                    // 조인트를 클릭했을 땐 연결된 자식 링크를 하이라이트 (혹은 부모+자식)
                    highlight3DComponents(node.components); 
                }
            }

            updateSelectedJointFrameVisibility();
            render(); 
        }

        function selectedJointMotionEditorHtml(joint) {
            if (!joint) return '';
            if (joint.joint_type === 'fixed') {
                return `
                    <div class="joint-fixed-settings">
                        <strong>fixed 조인트</strong><br>
                        움직이지 않는 고정 연결이므로 축·리밋·effort·velocity 설정이 필요하지 않습니다.
                    </div>
                `;
            }
            const index = previewJointControllers.findIndex(
                controller => controller.jointObj === joint
                    || controller.name === joint.joint_name
            );
            if (index < 0) return '';

            const controller = previewJointControllers[index];
            const jointInfo = controller.jointInfo || joint.joint_info || {};
            const isPrismatic = controller.type === 'prismatic';
            const isContinuous = controller.type === 'continuous';
            const lowerWasSet = jointInfo._manual_limit_lower_set === true;
            const upperWasSet = jointInfo._manual_limit_upper_set === true;
            const manualLimitPending = controller.type === 'revolute'
                && (lowerWasSet !== upperWasSet);
            let min = isPrismatic
                ? (Number.isFinite(controller.lowerLimit) ? controller.lowerLimit : -0.1)
                : -360;
            let max = isPrismatic
                ? (Number.isFinite(controller.upperLimit) ? controller.upperLimit : 0.1)
                : 360;
            const step = isPrismatic ? 0.001 : 1;
            if (!isPrismatic && controller.type === 'revolute' && !manualLimitPending) {
                if (Number.isFinite(controller.lowerLimit)) {
                    min = Math.round(controller.lowerLimit * 180 / Math.PI);
                }
                if (Number.isFinite(controller.upperLimit)) {
                    max = Math.round(controller.upperLimit * 180 / Math.PI);
                }
            }
            const currentValue = Math.max(min, Math.min(max, Number(controller.value) || 0));
            const lowerDegrees = Number.isFinite(Number(jointInfo.lower_limit))
                ? Number(jointInfo.lower_limit) * 180 / Math.PI
                : null;
            const upperDegrees = Number.isFinite(Number(jointInfo.upper_limit))
                ? Number(jointInfo.upper_limit) * 180 / Math.PI
                : null;
            const limitIsReady = controller.type === 'revolute'
                && !manualLimitPending
                && lowerDegrees !== null
                && upperDegrees !== null
                && upperDegrees > lowerDegrees;
            const importedLimitReady = controller.type === 'revolute'
                && !lowerWasSet
                && !upperWasSet
                && limitIsReady;
            const lowerInputValue = (lowerWasSet || importedLimitReady) && lowerDegrees !== null
                ? Number(lowerDegrees.toFixed(3))
                : '';
            const upperInputValue = (upperWasSet || importedLimitReady) && upperDegrees !== null
                ? Number(upperDegrees.toFixed(3))
                : '';
            const limitSummary = controller.type === 'continuous'
                ? '연속 회전 · 최소/최대 제한 없음'
                : (
                    limitIsReady
                        ? `허용 범위 ${lowerDegrees.toFixed(1)}° ~ ${upperDegrees.toFixed(1)}°`
                        : `리밋 지정 중 · 최소 ${lowerWasSet && lowerDegrees !== null ? `${lowerDegrees.toFixed(1)}°` : '미지정'} / 최대 ${upperWasSet && upperDegrees !== null ? `${upperDegrees.toFixed(1)}°` : '미지정'}`
                );
            const effortLimit = Number.isFinite(Number(jointInfo.effort_limit))
                && Number(jointInfo.effort_limit) > 0
                ? Number(jointInfo.effort_limit)
                : 100;
            const velocityLimit = Number.isFinite(Number(jointInfo.velocity_limit))
                && Number(jointInfo.velocity_limit) > 0
                ? Number(jointInfo.velocity_limit)
                : 1;
            const prismaticLower = Number.isFinite(Number(jointInfo.lower_limit))
                ? Number(jointInfo.lower_limit)
                : -0.1;
            const prismaticUpper = Number.isFinite(Number(jointInfo.upper_limit))
                ? Number(jointInfo.upper_limit)
                : 0.1;
            const effortUnit = isPrismatic ? 'N' : 'N·m';
            const velocityUnit = isPrismatic ? 'm/s' : 'rad/s';
            const zeroOffsetCalibration = Number(jointInfo._zero_offset_calibration);
            const hasZeroCalibration = Number.isFinite(zeroOffsetCalibration)
                && Math.abs(zeroOffsetCalibration) > 1e-12;
            const zeroOffsetDisplay = isPrismatic
                ? zeroOffsetCalibration
                : THREE.MathUtils.radToDeg(zeroOffsetCalibration);

            return `
                <div class="joint-control" style="margin-bottom:12px;">
                    <div class="joint-title">
                        <span>${controller.name}</span>
                        <span class="joint-badge-ui">${controller.type}</span>
                    </div>
                    <input class="joint-slider" type="range"
                           min="${min}" max="${max}" step="${step}" value="${currentValue}"
                           data-preview-joint="${index}"
                           onpointerdown="beginPreviewJointGesture(${index})"
                           onfocus="beginPreviewJointGesture(${index})"
                           oninput="setPreviewJointValue(${index}, Number(this.value))"
                           onchange="endPreviewJointGesture(${index})"
                           onblur="endPreviewJointGesture(${index})"
                           onwheel="event.preventDefault(); nudgePreviewJoint(${index}, event.deltaY < 0 ? 1 : -1)">
                    <div class="joint-value-row">
                        <span>${min}</span>
                        <div class="joint-fine-control">
                            ${isPrismatic ? '' : `<button type="button" onclick="nudgePreviewJoint(${index}, -1)">−1°</button>`}
                            <input class="joint-value joint-current-input"
                                   data-preview-joint-value="${index}" type="number" step="${step}"
                                   value="${Number.isInteger(currentValue) ? currentValue : currentValue.toFixed(3)}"
                                   onchange="commitPreviewJointValue(${index}, this)"
                                   onkeydown="handlePreviewJointValueKey(event, ${index})">
                            ${isPrismatic ? '' : `<button type="button" onclick="nudgePreviewJoint(${index}, 1)">+1°</button>`}
                        </div>
                        <span>${max}</span>
                    </div>
                    <button type="button" class="form-control"
                            data-set-joint-zero="${index}"
                            onclick="setPreviewJointZero(${index})"
                            ${Math.abs(currentValue) <= 1e-9 ? 'disabled' : ''}
                            title="현재 조립 자세를 유지한 채 이 위치를 URDF 조인트 0으로 다시 정의합니다."
                            style="cursor:pointer;margin-top:8px;border-color:#36b6d9;color:#dff8ff;background:#173d49;">
                        현재 ${Number.isInteger(currentValue) ? currentValue : currentValue.toFixed(3)}${isPrismatic ? ' m' : '°'} 자세를 0으로 설정
                    </button>
                    <div class="joint-limit-summary">
                        현재 자세는 유지하고 원점과 가동 범위를 함께 이동합니다.
                    </div>
                    ${hasZeroCalibration ? `
                    <button type="button" class="form-control"
                            onclick="revertPreviewJointZero(${index})"
                            title="베이크한 영점 오프셋과 하위 부품 변환을 함께 되돌립니다."
                            style="cursor:pointer;margin-top:6px;border-color:#d49a3a;color:#ffe9bf;background:#493519;">
                        영점 설정 취소 (${Number(zeroOffsetDisplay.toFixed(3))}${isPrismatic ? ' m' : '°'})
                    </button>` : ''}
                    ${isContinuous ? '<div class="joint-limit-summary">미리보기 조작 범위 · URDF 회전 제한 아님</div>' : ''}
                    <div class="joint-limit-editor joint-type-settings">
                        <div class="joint-parameter-heading">
                            <strong>URDF 동작 설정</strong>
                            <span>${controller.type}</span>
                        </div>
                    ${controller.type === 'revolute' ? `
                        <div class="joint-limit-actions">
                            <button type="button" onclick="setPreviewJointLimit(${index}, 'lower')">현재 ${currentValue}° → 최소</button>
                            <button type="button" onclick="setPreviewJointLimit(${index}, 'upper')">현재 ${currentValue}° → 최대</button>
                        </div>
                        <div class="joint-limit-inputs">
                            <label>최소°
                                <input type="number" step="0.1" value="${lowerInputValue}" placeholder="미지정"
                                       onchange="setPreviewJointLimitDegrees(${index}, 'lower', this.value)">
                            </label>
                            <label>최대°
                                <input type="number" step="0.1" value="${upperInputValue}" placeholder="미지정"
                                       onchange="setPreviewJointLimitDegrees(${index}, 'upper', this.value)">
                            </label>
                        </div>
                        <div class="joint-limit-summary ${manualLimitPending ? 'pending' : ''}">
                            ${limitSummary}
                        </div>
                    ` : ''}
                    ${isPrismatic ? `
                        <div class="joint-limit-inputs">
                            <label>최소 이동 (m)
                                <input type="number" step="0.001" value="${prismaticLower}"
                                       onchange="updateJointUrdfValue('${joint.joint_name}', 'lower_limit', this)">
                            </label>
                            <label>최대 이동 (m)
                                <input type="number" step="0.001" value="${prismaticUpper}"
                                       onchange="updateJointUrdfValue('${joint.joint_name}', 'upper_limit', this)">
                            </label>
                        </div>
                    ` : ''}
                    ${isContinuous ? `
                        <div class="joint-limit-summary">연속 회전이므로 lower/upper를 URDF에 출력하지 않습니다.</div>
                    ` : ''}
                        <div class="joint-required-inputs">
                            <label>최대 힘 (${effortUnit})
                                <input type="number" min="0.000001" step="0.1" value="${effortLimit}"
                                       onchange="updateJointUrdfValue('${joint.joint_name}', 'effort_limit', this)">
                            </label>
                            <label>최대 속도 (${velocityUnit})
                                <input type="number" min="0.000001" step="0.1" value="${velocityLimit}"
                                       onchange="updateJointUrdfValue('${joint.joint_name}', 'velocity_limit', this)">
                            </label>
                        </div>
                    </div>
                </div>
            `;
        }

        function physicalMaterialLibrary() {
            if (!treeData) return {};
            if (!treeData._physical_materials || typeof treeData._physical_materials !== 'object') {
                treeData._physical_materials = {};
            }
            return treeData._physical_materials;
        }

        function physicalMaterialAssignments() {
            if (!treeData) return {};
            if (!treeData._component_material_assignments || typeof treeData._component_material_assignments !== 'object') {
                treeData._component_material_assignments = {};
            }
            return treeData._component_material_assignments;
        }

        function materialColorHex(rgba) {
            const values = String(rgba || '').trim().split(/\s+/).slice(0, 3).map(Number);
            if (values.length !== 3 || values.some(value => !Number.isFinite(value))) return '#9ca3af';
            return '#' + values.map(value => Math.round(Math.max(0, Math.min(1, value)) * 255)
                .toString(16).padStart(2, '0')).join('');
        }

        function materialRgbaFromHex(hex) {
            const value = String(hex || '#9ca3af').replace('#', '');
            if (!/^[0-9a-fA-F]{6}$/.test(value)) return '0.612 0.639 0.686 1.000';
            return [0, 2, 4].map(index => (parseInt(value.slice(index, index + 2), 16) / 255).toFixed(3))
                .concat('1.000').join(' ');
        }

        function physicalMaterialCategoryOrder() {
            return [
                '금속', '플라스틱',
                '3D 프린팅 · 필라멘트', '3D 프린팅 · 레진', '3D 프린팅 · 분말/금속',
                '복합재·탄성체', '기타', '사용자 재질'
            ];
        }

        function groupedPhysicalMaterials(searchQuery = '') {
            const categoryOrder = physicalMaterialCategoryOrder();
            const grouped = new Map(categoryOrder.map(category => [category, []]));
            const normalizedQuery = String(searchQuery || '').trim().toLocaleLowerCase();
            Object.entries(physicalMaterialLibrary()).forEach(([key, material]) => {
                const category = String(material.category || (material.builtin ? '기타' : '사용자 재질'));
                const searchable = [
                    key,
                    material.name || '',
                    category,
                    Number(material.density || 0).toLocaleString(),
                    String(Number(material.density || 0)),
                ].join(' ').toLocaleLowerCase();
                if (normalizedQuery && !searchable.includes(normalizedQuery)) return;
                if (!grouped.has(category)) grouped.set(category, []);
                grouped.get(category).push([key, material]);
            });
            return grouped;
        }

        function patcherMaterialShelfCardsHtml() {
            const entries = [];
            groupedPhysicalMaterials(patcherMaterialShelfQuery).forEach(categoryEntries => {
                categoryEntries.forEach(entry => entries.push(entry));
            });
            const materialCards = entries.length ? entries.map(([key, material]) => `
                <div class="patcher-material-card" draggable="true"
                     data-material-key="${escapeHtmlText(key)}"
                     ondragstart="startPhysicalMaterialDrag(event, this)"
                     ondragend="finishPhysicalMaterialDrag()"
                     title="${escapeHtmlText(material.name || key)} 재질을 링크 전체에 적용">
                    <span class="material-drag-swatch" style="background:${materialColorHex(material.rgba)}"></span>
                    <span class="material-drag-copy">
                        <strong>${escapeHtmlText(material.name || key)}</strong>
                        <small>${Number(material.density || 0).toLocaleString()} kg/m³</small>
                    </span>
                    <span class="material-drag-grip" aria-hidden="true">⠿</span>
                </div>
            `).join('') : '<div class="patcher-material-empty">검색 결과가 없습니다.</div>';
            const addCard = `
                <button type="button" class="patcher-material-card patcher-material-add-card"
                        onclick="openPatcherMaterialCreator()"
                        title="새 사용자 재질 추가">
                    <span>＋</span><span>새 재질 추가</span>
                </button>
            `;
            const createForm = patcherMaterialCreateOpen ? `
                <div class="patcher-material-create">
                    <label>재질 이름
                        <input id="patcher-new-material-name" type="text" placeholder="예: TPU 95A"
                               onkeydown="if (event.key === 'Enter') createPhysicalMaterialFromShelf()">
                    </label>
                    <label>밀도 · kg/m³
                        <input id="patcher-new-material-density" type="number" min="0.001" step="1" value="1000">
                    </label>
                    <label>표시 색상
                        <input id="patcher-new-material-color" type="color" value="#9ca3af">
                    </label>
                    <div class="patcher-material-create-actions">
                        <button type="button" onclick="createPhysicalMaterialFromShelf()">추가</button>
                        <button type="button" onclick="closePatcherMaterialCreator()">취소</button>
                    </div>
                </div>
            ` : '';
            return materialCards + addCard + createForm;
        }

        function refreshPatcherMaterialShelfCards() {
            const search = document.getElementById('patcher-material-shelf-search');
            const cards = document.getElementById('patcher-material-shelf-cards');
            if (search) search.value = patcherMaterialShelfQuery;
            if (cards) cards.innerHTML = patcherMaterialShelfCardsHtml();
        }

        function openPatcherMaterialCreator() {
            patcherMaterialCreateOpen = true;
            refreshPatcherMaterialShelfCards();
            const input = document.getElementById('patcher-new-material-name');
            input?.focus();
            input?.scrollIntoView({ block: 'nearest' });
        }

        function closePatcherMaterialCreator() {
            patcherMaterialCreateOpen = false;
            refreshPatcherMaterialShelfCards();
        }

        function createPhysicalMaterialFromShelf() {
            if (!treeData) return;
            const name = String(document.getElementById('patcher-new-material-name')?.value || '').trim();
            const density = Number(document.getElementById('patcher-new-material-density')?.value);
            const color = document.getElementById('patcher-new-material-color')?.value || '#9ca3af';
            if (!name) return alert('재질 이름을 입력하세요.');
            if (!Number.isFinite(density) || density <= 0) {
                return alert('밀도는 0보다 큰 kg/m³ 값이어야 합니다.');
            }
            saveState();
            const library = physicalMaterialLibrary();
            let index = 1;
            let key = `custom_material_${index}`;
            while (library[key]) key = `custom_material_${++index}`;
            library[key] = {
                name,
                density,
                rgba: materialRgbaFromHex(color),
                category: '사용자 재질',
                builtin: false,
            };
            selectedPhysicalMaterialKey = key;
            patcherMaterialCreateOpen = false;
            patcherMaterialShelfQuery = '';
            refreshPatcherMaterialShelfCards();
            updatePanel();
            scheduleWorkspaceAutosave();
            const status = document.getElementById('patcher-validation');
            if (status) status.textContent = `'${name}' 재질을 추가했습니다. 링크 카드로 드래그해 적용하세요.`;
        }

        function syncPatcherMaterialShelf(root = document) {
            const controls = root.querySelector?.('#patcher-controls');
            const shelf = root.querySelector?.('#patcher-material-shelf');
            const toggle = root.querySelector?.('#patcher-material-shelf-toggle');
            const search = root.querySelector?.('#patcher-material-shelf-search');
            const cards = root.querySelector?.('#patcher-material-shelf-cards');
            if (!shelf || !toggle) return;
            shelf.hidden = !patcherMaterialShelfExpanded;
            controls?.classList.toggle('material-shelf-open', patcherMaterialShelfExpanded);
            toggle.classList.toggle('material-shelf-active', patcherMaterialShelfExpanded);
            toggle.textContent = patcherMaterialShelfExpanded ? '▴ 재질 라이브러리' : '▾ 재질 라이브러리';
            toggle.setAttribute('aria-expanded', String(patcherMaterialShelfExpanded));
            if (!patcherMaterialShelfExpanded) return;
            if (search) search.value = patcherMaterialShelfQuery;
            if (cards) cards.innerHTML = patcherMaterialShelfCardsHtml();
            requestAnimationFrame(positionPatcherMaterialShelf);
        }

        function positionPatcherMaterialShelf() {
            const controls = document.getElementById('patcher-controls');
            const toggle = document.getElementById('patcher-material-shelf-toggle');
            const shelf = document.getElementById('patcher-material-shelf');
            if (!controls || !toggle || !shelf || shelf.hidden) return;
            const preferredLeft = toggle.offsetLeft;
            const maxLeft = Math.max(0, controls.clientWidth - shelf.offsetWidth);
            shelf.style.left = `${Math.min(preferredLeft, maxLeft)}px`;
            shelf.style.right = 'auto';
        }

        function togglePatcherMaterialShelf() {
            patcherMaterialShelfExpanded = !patcherMaterialShelfExpanded;
            syncPatcherMaterialShelf(document);
            if (patcherMaterialShelfExpanded) {
                document.getElementById('patcher-material-shelf-search')?.focus();
            }
        }

        function filterPatcherMaterialShelf(query) {
            patcherMaterialShelfQuery = String(query || '');
            refreshPatcherMaterialShelfCards();
        }

        function physicalMaterialOptions(selectedKey, includeOriginal = false) {
            const original = includeOriginal
                ? `<option value="" ${selectedKey ? '' : 'selected'}>CAD 원본 재질 유지</option>`
                : '';
            return original + [...groupedPhysicalMaterials().entries()]
                .filter(([, entries]) => entries.length)
                .map(([category, entries]) => `
                    <optgroup label="${escapeHtmlText(category)}">
                        ${entries.map(([key, material]) => `
                            <option value="${escapeHtmlText(key)}" ${key === selectedKey ? 'selected' : ''}>
                                ${escapeHtmlText(material.name || key)} · ${Number(material.density || 0).toLocaleString()} kg/m³
                            </option>
                        `).join('')}
                    </optgroup>
                `).join('');
        }

        function physicalMaterialLabel(key) {
            if (!key) return 'CAD 원본 재질 유지';
            const material = physicalMaterialLibrary()[key];
            if (!material) return key;
            return `${material.name || key} · ${Number(material.density || 0).toLocaleString()} kg/m³`;
        }

        function componentMaterialPickerHtml(component, materialKey) {
            return `
                <button type="button" class="form-control physical-material-picker-trigger"
                        data-component="${escapeHtmlText(component)}"
                        data-material-key="${escapeHtmlText(materialKey)}"
                        onclick="openPhysicalMaterialPicker(this)">
                    <span>${escapeHtmlText(physicalMaterialLabel(materialKey))}</span>
                    <span>▼</span>
                </button>
            `;
        }

        function closePhysicalMaterialPicker() {
            document.getElementById('physical-material-popover')?.remove();
            activePhysicalMaterialComponent = null;
            activePhysicalMaterialKey = '';
        }

        function appendPhysicalMaterialOption(container, key, label, density = null) {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'physical-material-popover-option';
            if (key === activePhysicalMaterialKey) button.classList.add('active');
            const name = document.createElement('span');
            name.textContent = label;
            button.appendChild(name);
            if (density !== null) {
                const value = document.createElement('small');
                value.textContent = `${Number(density || 0).toLocaleString()} kg/m³`;
                button.appendChild(value);
            }
            button.onclick = event => {
                event.stopPropagation();
                choosePhysicalMaterial(key);
            };
            container.appendChild(button);
        }

        function renderPhysicalMaterialPickerResults(searchQuery = '') {
            const results = document.getElementById('physical-material-popover-results');
            if (!results) return;
            results.innerHTML = '';
            appendPhysicalMaterialOption(results, '', 'CAD 원본 재질 유지');
            let matchCount = 0;
            groupedPhysicalMaterials(searchQuery).forEach((entries, category) => {
                if (!entries.length) return;
                const heading = document.createElement('div');
                heading.className = 'physical-material-popover-category';
                heading.textContent = category;
                results.appendChild(heading);
                entries.forEach(([key, material]) => {
                    appendPhysicalMaterialOption(
                        results,
                        key,
                        material.name || key,
                        material.density,
                    );
                    matchCount++;
                });
            });
            if (!matchCount && String(searchQuery || '').trim()) {
                const empty = document.createElement('div');
                empty.className = 'physical-material-popover-empty';
                empty.textContent = '검색 결과가 없습니다.';
                results.appendChild(empty);
            }
        }

        function openPhysicalMaterialPicker(trigger) {
            if (!trigger) return;
            const component = trigger.dataset.component || '';
            const existing = document.getElementById('physical-material-popover');
            if (existing && activePhysicalMaterialComponent === component) {
                closePhysicalMaterialPicker();
                return;
            }
            closePhysicalMaterialPicker();
            activePhysicalMaterialComponent = component;
            activePhysicalMaterialKey = trigger.dataset.materialKey || '';

            const popover = document.createElement('div');
            popover.id = 'physical-material-popover';
            popover.className = 'physical-material-popover';
            popover.innerHTML = `
                <input class="physical-material-popover-search" type="search"
                       placeholder="재질 검색 · ABS, PLA, 레진, 밀도..."
                       aria-label="재질 검색">
                <div id="physical-material-popover-results" class="physical-material-popover-results"></div>
            `;
            document.body.appendChild(popover);
            const input = popover.querySelector('.physical-material-popover-search');
            input.oninput = () => renderPhysicalMaterialPickerResults(input.value);
            input.onkeydown = event => {
                if (event.key === 'Escape') closePhysicalMaterialPicker();
            };
            renderPhysicalMaterialPickerResults('');

            const rect = trigger.getBoundingClientRect();
            const width = Math.min(380, Math.max(300, rect.width));
            popover.style.width = `${width}px`;
            const left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));
            popover.style.left = `${left}px`;
            const availableBelow = window.innerHeight - rect.bottom - 8;
            const desiredHeight = Math.min(500, popover.offsetHeight || 500);
            const top = availableBelow >= Math.min(300, desiredHeight)
                ? rect.bottom + 4
                : Math.max(8, rect.top - desiredHeight - 4);
            popover.style.top = `${top}px`;
            input.focus();
        }

        function choosePhysicalMaterial(key) {
            if (!treeData || !activePhysicalMaterialComponent) return;
            saveState();
            const assignments = physicalMaterialAssignments();
            if (key) assignments[activePhysicalMaterialComponent] = key;
            else delete assignments[activePhysicalMaterialComponent];
            closePhysicalMaterialPicker();
            updatePanel();
            scheduleWorkspaceAutosave();
        }

        document.addEventListener('pointerdown', event => {
            const popover = document.getElementById('physical-material-popover');
            if (!popover) return;
            if (popover.contains(event.target)) return;
            if (event.target.closest?.('.physical-material-picker-trigger')) return;
            closePhysicalMaterialPicker();
        });
        document.addEventListener('keydown', event => {
            if (event.key === 'Escape') closePhysicalMaterialPicker();
        });
        window.addEventListener('resize', closePhysicalMaterialPicker);
        window.addEventListener('resize', positionPatcherMaterialShelf);

        function componentMaterialMassText(component, materialKey) {
            const snapshot = (treeData?._component_physical || {})[component] || {};
            const originalMass = Number(snapshot.mass);
            if (!materialKey) {
                return Number.isFinite(originalMass) ? `원본 ${originalMass.toFixed(3)} kg` : 'CAD 원본 물성';
            }
            const density = Number(physicalMaterialLibrary()[materialKey]?.density);
            let volume = Number(snapshot.volume_m3);
            if (!(volume > 0)) {
                const referenceDensity = Number(snapshot.density);
                if (originalMass > 0 && referenceDensity > 0) volume = originalMass / referenceDensity;
            }
            if (!(volume > 0) || !(density > 0)) return '체적 정보 없음 · 적용 시 경고';
            return `예상 질량 ${(volume * density).toFixed(3)} kg`;
        }

        function selectedMaterialEditorHtml() {
            const library = physicalMaterialLibrary();
            const keys = Object.keys(library);
            if (!selectedPhysicalMaterialKey || !library[selectedPhysicalMaterialKey]) {
                selectedPhysicalMaterialKey = keys[0] || null;
            }
            const material = selectedPhysicalMaterialKey ? library[selectedPhysicalMaterialKey] : null;
            return `
                <select class="form-control physical-material-select" data-include-original="0"
                        onchange="selectPhysicalMaterial(this.value)">
                    ${physicalMaterialOptions(selectedPhysicalMaterialKey, false)}
                </select>
                ${material ? `
                <div class="material-drag-card" draggable="true"
                     data-material-key="${escapeHtmlText(selectedPhysicalMaterialKey)}"
                     ondragstart="startPhysicalMaterialDrag(event, this)"
                     ondragend="finishPhysicalMaterialDrag()"
                     title="로봇 구조 트리의 링크 카드에 놓으면 포함된 모든 부품에 적용됩니다.">
                    <span class="material-drag-swatch" style="background:${materialColorHex(material.rgba)}"></span>
                    <span class="material-drag-copy">
                        <strong>${escapeHtmlText(material.name || selectedPhysicalMaterialKey)}</strong>
                        <small>링크로 드래그 · 모든 부품에 일괄 적용</small>
                    </span>
                    <span class="material-drag-grip" aria-hidden="true">⠿</span>
                </div>` : ''}
                <div class="material-library-grid">
                    <label>재질 이름
                        <input id="physical-material-name" class="form-control" type="text"
                               value="${escapeHtmlText(material?.name || '')}" placeholder="새 재질">
                    </label>
                    <label>밀도 · kg/m³
                        <input id="physical-material-density" class="form-control" type="number"
                               min="0.001" step="1" value="${Number(material?.density || 1000)}">
                    </label>
                    <label>표시 색상
                        <input id="physical-material-color" class="form-control" type="color"
                               value="${materialColorHex(material?.rgba)}">
                    </label>
                </div>
                <div class="material-library-actions">
                    <button type="button" class="form-control" onclick="createPhysicalMaterial()">＋ 추가</button>
                    <button type="button" class="form-control" onclick="savePhysicalMaterial()"
                            style="border-color:#39a96b;color:#c9ffe0;">저장</button>
                    <button type="button" class="form-control" onclick="deletePhysicalMaterial()"
                            ${material?.builtin ? 'disabled title="기본 재질은 삭제할 수 없습니다."' : ''}
                            style="border-color:#9b5a5a;color:#ffd0d0;">삭제</button>
                </div>
            `;
        }

        function componentMaterialEditorHtml(node) {
            return `
                <details class="material-library-details"
                         ${physicalMaterialLibraryExpanded ? 'open' : ''}
                         ontoggle="setPhysicalMaterialLibraryExpanded(this.open)">
                    <summary>
                        <span>재질 라이브러리</span>
                        <small>${Object.keys(physicalMaterialLibrary()).length}개 · 열어서 추가·수정</small>
                    </summary>
                    <div class="material-library-content">
                        ${selectedMaterialEditorHtml()}
                    </div>
                </details>
            `;
        }

        function setPhysicalMaterialLibraryExpanded(expanded) {
            physicalMaterialLibraryExpanded = !!expanded;
        }

        function startPhysicalMaterialDrag(event, source) {
            const key = source?.dataset?.materialKey || '';
            if (!key || !physicalMaterialLibrary()[key]) {
                event.preventDefault();
                return;
            }
            closePhysicalMaterialPicker();
            draggedNode = null;
            draggedPhysicalMaterialKey = key;
            draggedPhysicalMaterialSource = source;
            source.classList.add('dragging');
            document.body.classList.add('material-dragging');
            event.dataTransfer.effectAllowed = 'copy';
            event.dataTransfer.setData('application/x-petasos-material', key);
            event.dataTransfer.setData('text/plain', physicalMaterialLabel(key));
        }

        function finishPhysicalMaterialDrag() {
            draggedPhysicalMaterialSource?.classList.remove('dragging');
            draggedPhysicalMaterialSource = null;
            draggedPhysicalMaterialKey = null;
            document.body.classList.remove('material-dragging');
            if (currentDragOverElement) {
                currentDragOverElement.classList.remove('drag-over', 'material-drop-target');
                currentDragOverElement = null;
            }
            document.querySelectorAll('.material-drop-target').forEach(element => {
                element.classList.remove('material-drop-target');
            });
        }

        function applyPhysicalMaterialToLink(node, materialKey) {
            const material = physicalMaterialLibrary()[materialKey];
            const components = Array.isArray(node?.components) ? node.components : [];
            if (!material || !components.length) return false;
            saveState();
            const assignments = physicalMaterialAssignments();
            components.forEach(component => assignments[component] = materialKey);
            selectedElement = { type: 'link', node, jointObj: null };
            render({ skipPreview: true });
            const status = document.getElementById('patcher-validation');
            if (status) {
                status.textContent = `${node.name}: ${components.length}개 부품에 '${material.name || materialKey}' 재질을 적용했습니다.`;
            }
            return true;
        }

        function attachPhysicalMaterialDropEvents(domElement, node) {
            domElement.ondragover = event => {
                if (!draggedPhysicalMaterialKey) return;
                event.preventDefault();
                event.stopPropagation();
                event.dataTransfer.dropEffect = 'copy';
                if (currentDragOverElement && currentDragOverElement !== domElement) {
                    currentDragOverElement.classList.remove('drag-over', 'material-drop-target');
                }
                currentDragOverElement = domElement;
                domElement.classList.add('material-drop-target');
            };
            domElement.ondragleave = event => {
                if (!draggedPhysicalMaterialKey || domElement.contains(event.relatedTarget)) return;
                domElement.classList.remove('material-drop-target');
                if (currentDragOverElement === domElement) currentDragOverElement = null;
            };
            domElement.ondrop = event => {
                const materialKey = draggedPhysicalMaterialKey || event.dataTransfer.getData('application/x-petasos-material');
                if (!materialKey) return;
                event.preventDefault();
                event.stopPropagation();
                applyPhysicalMaterialToLink(node, materialKey);
                finishPhysicalMaterialDrag();
            };
        }

        function selectPhysicalMaterial(key) {
            selectedPhysicalMaterialKey = key || null;
            updatePanel();
        }

        function createPhysicalMaterial() {
            if (!treeData) return;
            saveState();
            const library = physicalMaterialLibrary();
            let index = 1;
            let key = `custom_material_${index}`;
            while (library[key]) key = `custom_material_${++index}`;
            library[key] = {
                name: `사용자 재질 ${index}`,
                density: 1000,
                rgba: '0.612 0.639 0.686 1.000',
                category: '사용자 재질',
                builtin: false,
            };
            selectedPhysicalMaterialKey = key;
            updatePanel();
            scheduleWorkspaceAutosave();
            document.getElementById('physical-material-name')?.focus();
        }

        function savePhysicalMaterial() {
            const material = physicalMaterialLibrary()[selectedPhysicalMaterialKey];
            if (!material) return;
            const name = String(document.getElementById('physical-material-name')?.value || '').trim();
            const density = Number(document.getElementById('physical-material-density')?.value);
            const color = document.getElementById('physical-material-color')?.value;
            if (!name) return alert('재질 이름을 입력하세요.');
            if (!Number.isFinite(density) || density <= 0) return alert('밀도는 0보다 큰 kg/m³ 값이어야 합니다.');
            saveState();
            material.name = name;
            material.density = density;
            material.rgba = materialRgbaFromHex(color);
            updatePanel();
            scheduleWorkspaceAutosave();
        }

        function deletePhysicalMaterial() {
            const library = physicalMaterialLibrary();
            const key = selectedPhysicalMaterialKey;
            if (!key || !library[key]) return;
            if (library[key].builtin) return alert('기본 재질은 삭제할 수 없습니다. 이름·밀도·색상은 수정할 수 있습니다.');
            if (!confirm(`'${library[key].name || key}' 재질을 삭제할까요? 지정된 부품은 CAD 원본 재질로 돌아갑니다.`)) return;
            saveState();
            delete library[key];
            const assignments = physicalMaterialAssignments();
            Object.keys(assignments).forEach(component => {
                if (assignments[component] === key) delete assignments[component];
            });
            selectedPhysicalMaterialKey = Object.keys(library)[0] || null;
            updatePanel();
            scheduleWorkspaceAutosave();
        }

        function updatePanel() {
            const body = document.getElementById('panel-body');
            const nextPanelSelectionIdentity = selectedElement?.controller || selectedElement?.jointObj || selectedElement?.node || null;
            if (nextPanelSelectionIdentity !== panelSelectionIdentity) {
                panelSelectionIdentity = nextPanelSelectionIdentity;
                queueMicrotask(() => {
                    if (body) body.scrollTop = 0;
                });
            }
            const panelHeader = document.getElementById('selected-properties-header');
            if (panelHeader) {
                const jointSelected = selectedElement?.type === 'joint' && selectedElement.jointObj;
                const controllerSelected = selectedElement?.type === 'controller' && selectedElement.controller;
                panelHeader.classList.toggle('joint-selected', !!jointSelected || !!controllerSelected);
                panelHeader.textContent = jointSelected
                    ? `조인트 속성 · ${selectedElement.jointObj.joint_name}`
                    : controllerSelected
                        ? `컨트롤러 속성 · ${selectedElement.controller.name}`
                        : '선택된 항목 속성';
            }
            if (!selectedElement) {
                body.innerHTML = `
                    <div class="empty-state">왼쪽 구조 트리나 아래 리스트에서 항목을 클릭하여<br>상세 속성을 편집하세요.</div>
                `;
                return;
            }

            if (selectedElement.type === 'controller') {
                const controller = selectedElement.controller;
                const activeJointNames = new Set(
                    patcherEntries().slice(1)
                        .filter(entry => entry.jointObj && entry.jointObj.joint_type !== 'fixed')
                        .map(entry => entry.jointObj.joint_name)
                );
                const joints = (controller.joints || []).filter(name => activeJointNames.has(name));
                const controllerColor = controller.color || CONTROLLER_PALETTE[0];
                const controllerTypeLabel = (CONTROLLER_TYPES.find(option => option[0] === controller.type) || CONTROLLER_TYPES[0])[1];
                const controllerSpecificHtml = controllerSpecificSettingsHtml(controller, joints);
                body.innerHTML = `
                    <div class="joint-selection-hero" style="border-left-color:${controllerColor};background:${controllerColorRgba(controllerColor, 0.14)};">
                        <div>
                            <strong>${escapeHtmlText(controller.name || 'controller')}</strong>
                            <small>${escapeHtmlText(controllerTypeLabel)} · ${joints.length}개 조인트</small>
                        </div>
                    </div>
                    <div class="joint-property-card">
                        <div class="joint-property-title">Controller Properties</div>
                        <section class="joint-property-section">
                            ${controllerTypeEditorHtml(controller)}
                        </section>
                        <section class="joint-property-section">
                            <div class="joint-property-section-title">GENERAL</div>
                            <label style="font-size:9px;color:#9fadb4;">Name
                                <input type="text" class="form-control"
                                       value="${escapeHtmlText(controller.name || '')}"
                                       onchange="updateSelectedControllerName(this.value)">
                            </label>
                            <div style="margin-top:9px;font-size:9px;color:#9fadb4;">Controlled Joints</div>
                            <div class="parts-list" style="margin-top:4px;">
                                ${joints.map(name => `<div>${escapeHtmlText(name)}</div>`).join('') || '<div>가동 조인트 없음</div>'}
                            </div>
                        </section>
                        ${controllerSpecificHtml ? `<section class="joint-property-section">${controllerSpecificHtml}</section>` : ''}
                    </div>
                    <button type="button" class="form-control" onclick="deleteSelectedController()"
                            style="cursor:pointer;margin-top:12px;border-color:#a94e5d;color:#ffd4da;background:#4b2028;">
                        컨트롤러 테두리 해제
                    </button>
                `;
            } else if (selectedElement.type === 'link') {
                const node = selectedElement.node;
                const linkDisabled = isLinkDisabled(node);
                const toggleBtnHtml = node === treeData ? '' : `
                    <div class="form-group" style="margin-bottom: 12px;">
                        <button type="button" class="form-control" onclick="toggleLinkActive(selectedElement.node)"
                                style="cursor:pointer;display:flex;align-items:center;justify-content:center;gap:10px;font-weight:bold;height:34px;
                                       ${linkDisabled
                                         ? 'border-color:#555e68;color:#cbd5e1;background:#262d35;'
                                         : 'border-color:#22c55e;color:#e8fdf0;background:#143823;box-shadow:0 0 8px rgba(34,197,94,0.25);'}">
                            <span class="patcher-node-toggle${linkDisabled ? ' is-disabled' : ''}" style="pointer-events:none;"><span class="toggle-knob"></span></span>
                            <span>${linkDisabled ? '링크 비활성화됨 (클릭 시 활성화 및 3D 모델 표시)' : '링크 활성화 중 (클릭 시 비활성화 및 3D 모델 숨김)'}</span>
                        </button>
                    </div>
                `;
                const assignments = physicalMaterialAssignments();
                let partsHtml = node.components.map((component, componentIndex) => {
                    const materialKey = assignments[component] || '';
                    return `
                    <div class="component-material-row">
                        <div class="component-material-copy">
                            <strong title="${escapeHtmlText(component)}">${escapeHtmlText(component)}</strong>
                            <small>${componentMaterialMassText(component, materialKey)}</small>
                        </div>
                        ${componentMaterialPickerHtml(component, materialKey)}
                        ${node.components.length > 1 ? `
                        <button type="button" class="link-part-remove"
                                title="${escapeHtmlText(component)} 부품을 이 링크에서 분리"
                                aria-label="${escapeHtmlText(component)} 부품 빼기"
                                onclick="event.stopPropagation(); extractComponentFromPatcherLink(selectedElement.node, selectedElement.node.components[${componentIndex}])">
                            ⊖
                        </button>` : ''}
                    </div>
                `;}).join('');
                let finalizeAlert = node.is_finalized ? 
                    `<div style="color:var(--accent-green); font-weight:bold; margin-bottom:10px;">✅ URDF 공식 링크로 확정됨</div>` : 
                    `<div style="color:#aaa; margin-bottom:10px;">⚠️ 아직 그룹화/확정되지 않은 부품</div>`;
                
                body.innerHTML = `
                    ${toggleBtnHtml}
                    ${finalizeAlert}
                    <div class="form-group">
                        <label>대표 링크 이름 (URDF)</label>
                        <input type="text" class="form-control" value="${node.name}" onchange="updateNodeName('${node.name}', this.value)">
                    </div>
                    <div class="form-group">
                        <label>통합 부품 · 물리 재질 (${node.components.length}개)</label>
                        <div class="parts-list">${partsHtml}</div>
                    </div>
                    ${componentMaterialEditorHtml(node)}
                    ${(node.components || []).length > 1 ? `
                    <button type="button" class="form-control"
                            onclick="ungroupPatcherLink(selectedElement.node)"
                            style="cursor:pointer;margin-top:14px;border-color:#e6a23c;color:#ffe0ad;background:#4a3216;">
                        ↗ 이 링크 그룹 해제
                    </button>` : ''}
                `;
            } else if (selectedElement.type === 'joint') {
                const joint = selectedElement.jointObj;
                let optionsHtml = ['fixed', 'revolute', 'continuous', 'prismatic'].map(t => 
                    `<option value="${t}" ${joint.joint_type === t ? 'selected' : ''}>${t}</option>`
                ).join('');

                const jointInfo = joint.joint_info || {};
                joint.joint_info = jointInfo;
                ensureJointCadTransformSnapshot(jointInfo);
                const motionEditorHtml = selectedJointMotionEditorHtml(joint);
                const groupCandidate = isPatcherGroupCandidate(joint);
                const axisValues = jointInfo.axis || [0, 0, 1];
                const rpyValues = jointInfo._manual_rpy || jointInfo.rpy || [0, 0, 0];
                const xyzValues = Array.isArray(jointInfo.xyz) ? jointInfo.xyz : [0, 0, 0];
                const parentLinkName = jointInfo.parent || '미연결';
                const childLinkName = jointInfo.child || selectedElement.node?.name || '미연결';
                const maxAcceleration = optionalJointNumberValue(jointInfo.max_acceleration);
                const maxDeceleration = optionalJointNumberValue(jointInfo.max_deceleration);
                const maxJerk = optionalJointNumberValue(jointInfo.max_jerk);
                const damping = optionalJointNumberValue(jointInfo.damping);
                const friction = optionalJointNumberValue(jointInfo.friction);
                const mimicJoint = String(jointInfo.mimic_joint || '');
                const mimicMultiplier = Number.isFinite(Number(jointInfo.mimic_multiplier)) ? Number(jointInfo.mimic_multiplier) : 1;
                const mimicOffset = Number.isFinite(Number(jointInfo.mimic_offset)) ? Number(jointInfo.mimic_offset) : 0;
                const commandInterface = ['position', 'velocity', 'effort'].includes(jointInfo.command_interface)
                    ? jointInfo.command_interface : 'position';
                const stateInterfaces = Array.isArray(jointInfo.state_interfaces)
                    ? jointInfo.state_interfaces : ['position'];
                const mimicJointOptions = getFlatLinks(treeData, null, -1)
                    .map(item => item.jointObj)
                    .filter(candidate => candidate && candidate !== joint && candidate.joint_type !== 'fixed')
                    .map(candidate => `<option value="${escapeHtmlText(candidate.joint_name)}" ${candidate.joint_name === mimicJoint ? 'selected' : ''}>${escapeHtmlText(candidate.joint_name)}</option>`)
                    .join('');
                const axisType = getPanelAxisType(axisValues);
                const axisCandidates = jointInfo._axis_candidates || [];
                const jointSnap = jointInfo._joint_snap || null;
                const jointPointText = Array.isArray(jointInfo._preview_world_xyz)
                    ? jointInfo._preview_world_xyz.map(value => Number(value).toFixed(4)).join(', ')
                    : null;
                const jointSnapSummary = jointSnap
                    ? `${jointSnap.component} · [${jointPointText || '0, 0, 0'}] m · ${
                        jointSnap.source === 'opencascade'
                            ? `OpenCascade 정확 스냅 (${jointSnap.cad_feature_type || 'CAD 형상'})`
                            : '메쉬 면 중심/법선'
                    }으로 설정됨`
                    : '아직 3D에서 다시 지정하지 않았습니다.';
                const axisCandidateOptions = axisCandidates.map((candidate, candidateIndex) => `
                            <option value="${candidateIndex}" ${JSON.stringify(candidate.axis) === JSON.stringify(axisValues) ? 'selected' : ''}>${candidate.label}: [${candidate.axis.join(', ')}]</option>
                        `).join('');
                const jointPickComponents = selectedElement.node
                    ? selectedElement.node.components || []
                    : [];
                const jointPickComponentOptions = jointPickComponents.map(
                    (component, componentIndex) => `
                        <option value="${componentIndex}">${component}</option>
                    `
                ).join('');
                const jointOriginToolsHtml = `
                    <div class="joint-origin-toolbox">
                    <div class="hint-box green" style="margin-bottom:8px;">
                        <strong>조인트 원점·축 재설정</strong><br>
                        <span id="joint-origin-pick-help">${jointSnapSummary}</span>
                    </div>
                    <button id="joint-origin-pick-button" type="button" class="form-control"
                            onclick="toggleJointOriginPick()"
                            style="cursor:pointer;border-color:#27b8ff;color:#e0f6ff;background:#174b61;margin-bottom:6px;">
                        🎯 3D에서 조인트 중심·축 다시 찍기
                    </button>
                    <button type="button" class="form-control"
                            onclick="restoreImportedAssemblyPose(true)"
                            style="cursor:pointer;border-color:#64748b;color:#eef4ff;background:#29333d;margin-bottom:6px;">
                        ↺ 조립품 원래 자세로 복원
                    </button>
                    <div id="joint-origin-pick-tools" style="display:none;border:1px solid #3a7188;background:#152a32;border-radius:5px;padding:8px;margin-bottom:8px;">
                        <label style="display:block;margin-bottom:4px;">클릭 판정에 남길 부품</label>
                        <select id="joint-pick-component-select" class="form-control"
                                onchange="setJointPickComponentScope(this.value)"
                                style="margin-bottom:5px;">
                            <option value="-1">자식 링크 전체 (${jointPickComponents.length}개 부품)</option>
                            ${jointPickComponentOptions}
                        </select>
                        <div id="joint-pick-scope-summary" style="font-size:11px;color:#9fd8ef;margin-bottom:8px;"></div>
                        <label style="display:block;margin-bottom:4px;">겹친 자석 선택</label>
                        <select id="joint-snap-candidate-select" class="form-control"
                                onchange="selectJointSnapCandidate(this.value)"
                                style="margin-bottom:5px;">
                            <option value="-1">마우스를 원·호 위로 옮기세요</option>
                        </select>
                        <div style="display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-bottom:5px;">
                            <button type="button" class="form-control" onclick="cycleJointSnapCandidate(-1)"
                                    style="cursor:pointer;background:#263f49;">◀ 이전 자석</button>
                            <button type="button" class="form-control" onclick="cycleJointSnapCandidate(1)"
                                    style="cursor:pointer;background:#263f49;">다음 자석 ▶</button>
                        </div>
                        <div id="joint-snap-candidate-summary" style="font-size:11px;color:#ffd56a;"></div>
                    </div>
                    <button type="button" class="form-control" onclick="flipSelectedJointAxis()"
                            style="cursor:pointer;border-color:#777;color:#eee;background:#30363a;margin-bottom:12px;">
                        ↕ 조인트 축 방향 뒤집기
                    </button>
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:12px;">
                        <button type="button" class="form-control" onclick="isolateSelectedJointChild()"
                                style="cursor:pointer;border-color:#7c9cff;color:#e8eeff;background:#273454;">
                            👁 자식 링크만 보기
                        </button>
                        <button type="button" class="form-control" onclick="showAllViewerParts()"
                                style="cursor:pointer;border-color:#666;color:#eee;background:#30363a;">
                            🌐 전체 부품 보기
                        </button>
                    </div>
                    </div>
                `;

                const jointDisabled = isJointDisabled(joint);
                const jointToggleBtnHtml = `
                    <div class="form-group" style="margin-bottom: 12px;">
                        <button type="button" class="form-control" onclick="toggleJointActive(selectedElement.jointObj)"
                                style="cursor:pointer;display:flex;align-items:center;justify-content:center;gap:10px;font-weight:bold;height:34px;
                                       ${jointDisabled
                                         ? 'border-color:#555e68;color:#cbd5e1;background:#262d35;'
                                         : 'border-color:#22c55e;color:#e8fdf0;background:#143823;box-shadow:0 0 8px rgba(34,197,94,0.25);'}">
                            <span class="patcher-node-toggle${jointDisabled ? ' is-disabled' : ''}" style="pointer-events:none;"><span class="toggle-knob"></span></span>
                            <span>${jointDisabled ? '조인트 비활성화됨 (클릭 시 활성화 및 3D 모델 표시)' : '조인트 활성화 중 (클릭 시 비활성화 및 3D 모델 숨김)'}</span>
                        </button>
                    </div>
                `;

                body.innerHTML = `
                    ${jointOriginToolsHtml}
                    ${jointToggleBtnHtml}
                    <div class="joint-selection-hero">
                        <span class="joint-selection-badge">JOINT</span>
                        <strong>${escapeHtmlText(joint.joint_name)}</strong>
                        <small>${escapeHtmlText(parentLinkName)} → ${escapeHtmlText(childLinkName)} · ${escapeHtmlText(joint.joint_type)}</small>
                    </div>
                    <div class="joint-property-card">
                        <div class="joint-property-title">Joint Properties</div>
                        <section class="joint-property-section">
                            <div class="joint-property-section-title">GENERAL</div>
                            <div class="joint-property-grid">
                                <label>Name
                                    <input type="text" class="form-control" value="${escapeHtmlText(joint.joint_name)}"
                                           onchange="updateJointName('${escapeHtmlText(joint.joint_name)}', this.value)">
                                </label>
                                <span class="joint-general-spacer" aria-hidden="true"></span>
                                <label>Parent<div class="joint-property-readonly" title="${escapeHtmlText(parentLinkName)}">${escapeHtmlText(parentLinkName)}</div></label>
                                <label>Child<div class="joint-property-readonly" title="${escapeHtmlText(childLinkName)}">${escapeHtmlText(childLinkName)}</div></label>
                            </div>
                        </section>
                        <section class="joint-property-section">
                            <div class="joint-property-section-title">ORIGIN</div>
                            <div class="joint-property-grid three">
                                ${['X', 'Y', 'Z'].map((label, axisIndex) => `
                                <label>${label} · m
                                    <input class="form-control" type="number" step="0.001" value="${Number(xyzValues[axisIndex] || 0)}"
                                           onchange="updateJointXyzVal('${escapeHtmlText(joint.joint_name)}', ${axisIndex}, this.value)">
                                </label>`).join('')}
                            </div>
                            <div class="joint-property-grid three" style="margin-top:6px;">
                                ${['R', 'P', 'Y'].map((label, axisIndex) => `
                                <label>${label} · deg
                                    <input class="form-control" type="number" step="1" value="${(Number(rpyValues[axisIndex] || 0) * 180 / Math.PI).toFixed(1)}"
                                           onchange="updateJointRpyVal('${escapeHtmlText(joint.joint_name)}', ${axisIndex}, this.value)">
                                </label>`).join('')}
                            </div>
                            <button type="button" class="form-control joint-cad-transform-button"
                                    onclick="restoreSelectedJointCadTransform()">↺ CAD Transform 사용</button>
                        </section>
                    </div>
                    ${groupCandidate ? `
                    <div class="hint-box green" style="margin-bottom:12px;">
                        🧲 이 연결은 IAM 배치 보존용 묶음 후보입니다.<br>
                        같은 링크의 부품이면 카드를 겹쳐 합치고, 서로 움직이는 링크 사이면 아래 버튼으로 실제 조인트로 전환하세요.
                    </div>
                    <button type="button" class="form-control" onclick="activateSelectedJoint()"
                            style="cursor:pointer;border-color:#38bdf8;color:#e0f6ff;background:#174b61;margin-bottom:12px;">
                        ⚙️ 이 연결을 실제 조인트로 사용
                    </button>` : ''}
                    <div class="form-group">
                        <label>MECHANISM · Joint Type</label>
                        <select class="form-control" onchange="updateJointType('${joint.joint_name}', this.value)">
                            ${optionsHtml}
                        </select>
                    </div>
                    ${motionEditorHtml}
                    ${joint.joint_type === 'fixed' ? '' : `
                    <div class="form-group">
                        <label>회전/이동 축 (Axis)</label>
                        <select class="form-control" onchange="updateJointAxisType('${joint.joint_name}', this.value)">
                            <option value="x" ${axisType === 'x' ? 'selected' : ''}>+X [1, 0, 0]</option>
                            <option value="nx" ${axisType === 'nx' ? 'selected' : ''}>-X [-1, 0, 0]</option>
                            <option value="y" ${axisType === 'y' ? 'selected' : ''}>+Y [0, 1, 0]</option>
                            <option value="ny" ${axisType === 'ny' ? 'selected' : ''}>-Y [0, -1, 0]</option>
                            <option value="z" ${axisType === 'z' ? 'selected' : ''}>+Z [0, 0, 1]</option>
                            <option value="nz" ${axisType === 'nz' ? 'selected' : ''}>-Z [0, 0, -1]</option>
                            <option value="custom" ${axisType === 'custom' ? 'selected' : ''}>Custom</option>
                        </select>
                    </div>
                    <div id="panel-custom-axis" style="display: ${axisType === 'custom' ? 'grid' : 'none'}; grid-template-columns: repeat(3, 1fr); gap: 4px; margin-top: -8px; margin-bottom: 12px;">
                         <input class="form-control" type="number" step="0.1" value="${axisValues[0]}" onchange="updateJointAxisVal('${joint.joint_name}', 'x', this.value)">
                         <input class="form-control" type="number" step="0.1" value="${axisValues[1]}" onchange="updateJointAxisVal('${joint.joint_name}', 'y', this.value)">
                         <input class="form-control" type="number" step="0.1" value="${axisValues[2]}" onchange="updateJointAxisVal('${joint.joint_name}', 'z', this.value)">
                    </div>
                    ${axisCandidateOptions ? `
                    <div class="form-group">
                        <label>Fusion 축 후보</label>
                        <select class="form-control" onchange="updateJointAxisCandidate('${joint.joint_name}', this.value)">
                            ${axisCandidateOptions}
                        </select>
                    </div>` : ''}
                    `}
                    ${joint.joint_type === 'fixed' ? '' : `
                    <details class="joint-property-details">
                        <summary>Advanced · 가감속 및 Jerk</summary>
                        <div class="joint-property-details-body joint-property-grid three">
                            <label>Acceleration
                                <input class="form-control" type="number" min="0" step="0.1" value="${maxAcceleration}"
                                       placeholder="미지정" onchange="updateOptionalJointNumber('max_acceleration', this, true)">
                            </label>
                            <label>Deceleration
                                <input class="form-control" type="number" min="0" step="0.1" value="${maxDeceleration}"
                                       placeholder="미지정" onchange="updateOptionalJointNumber('max_deceleration', this, true)">
                            </label>
                            <label>Jerk
                                <input class="form-control" type="number" min="0" step="0.1" value="${maxJerk}"
                                       placeholder="미지정" onchange="updateOptionalJointNumber('max_jerk', this, true)">
                            </label>
                        </div>
                    </details>
                    <details class="joint-property-details">
                        <summary>DYNAMICS</summary>
                        <div class="joint-property-details-body joint-property-grid">
                            <label>Damping
                                <input class="form-control" type="number" min="0" step="0.01" value="${damping}"
                                       placeholder="미지정" onchange="updateOptionalJointNumber('damping', this, false)">
                            </label>
                            <label>Friction
                                <input class="form-control" type="number" min="0" step="0.01" value="${friction}"
                                       placeholder="미지정" onchange="updateOptionalJointNumber('friction', this, false)">
                            </label>
                        </div>
                    </details>
                    <details class="joint-property-details">
                        <summary>MIMIC</summary>
                        <div class="joint-property-details-body">
                            <label style="font-size:9px;color:#9fadb4;">Mimic Joint
                                <select class="form-control" onchange="updateSelectedJointTextValue('mimic_joint', this.value)">
                                    <option value="">None</option>${mimicJointOptions}
                                </select>
                            </label>
                            <div class="joint-property-grid" style="margin-top:6px;">
                                <label>Multiplier
                                    <input class="form-control" type="number" step="0.1" value="${mimicMultiplier}"
                                           onchange="updateOptionalJointNumber('mimic_multiplier', this, false, 1)">
                                </label>
                                <label>Offset
                                    <input class="form-control" type="number" step="0.1" value="${mimicOffset}"
                                           onchange="updateOptionalJointNumber('mimic_offset', this, false, 0)">
                                </label>
                            </div>
                        </div>
                    </details>
                    <div class="joint-property-card" style="margin-top:8px;">
                        <div class="joint-property-section-title">CONTROL</div>
                        <label style="font-size:9px;color:#9fadb4;">Command Interface
                            <select class="form-control" onchange="updateSelectedJointTextValue('command_interface', this.value)">
                                ${['position', 'velocity', 'effort'].map(value => `<option value="${value}" ${value === commandInterface ? 'selected' : ''}>${value}</option>`).join('')}
                            </select>
                        </label>
                        <div class="joint-interface-checks">
                            ${['position', 'velocity', 'effort'].map(value => `
                            <label><input type="checkbox" ${stateInterfaces.includes(value) ? 'checked' : ''}
                                          onchange="updateJointStateInterface('${value}', this.checked)"> ${value}</label>`).join('')}
                        </div>
                    </div>`}
                    ${groupCandidate ? '' : `<button type="button" class="form-control" onclick="disconnectSelectedJoint()"
                            style="cursor:pointer;border-color:#9b5a32;color:#ffd0b0;background:#4a2418;">
                        ✂ 이 조인트 배선 끊기
                    </button>`}
                `;
            }
        }

        function escapeHtmlText(value) {
            return String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }

        function normalizedLinkName(value) {
            return String(value || '')
                .trim()
                .replace(/\\s+/g, '_')
                .replace(/[^A-Za-z0-9_-]/g, '_')
                .replace(/_+/g, '_')
                .replace(/^[-0-9]+/, '')
                .slice(0, 80);
        }

        function renameLinkNode(node, requestedName) {
            if (!treeData || !node) return false;
            const nextName = normalizedLinkName(requestedName);
            if (!nextName || nextName === node.name) return false;
            const duplicate = getFlatLinks(treeData, null, -1).some(
                item => item.node !== node && item.node.name === nextName
            );
            if (duplicate) {
                const status = document.getElementById('patcher-validation');
                if (status) status.textContent = `링크 이름 '${nextName}'은 이미 사용 중입니다.`;
                return false;
            }
            saveState();
            node.name = nextName;
            getFlatLinks(treeData, null, -1).forEach(item => {
                if (!item.jointObj) return;
                item.jointObj.joint_info = item.jointObj.joint_info || {};
                if (item.parentNode === node) item.jointObj.joint_info.parent = nextName;
                if (item.node === node) item.jointObj.joint_info.child = nextName;
            });
            previewControlsDirty = true;
            render({ previewDelay: 40 });
            return true;
        }

        function startPatcherLinkRename(event, node, titleElement) {
            event.preventDefault();
            event.stopPropagation();
            const header = titleElement && titleElement.parentElement;
            if (!header || header.querySelector('.patcher-node-name-input')) return;
            const input = document.createElement('input');
            input.className = 'patcher-node-name-input';
            input.value = node.name;
            input.setAttribute('aria-label', `${node.name} 링크 이름`);
            input.onpointerdown = innerEvent => innerEvent.stopPropagation();
            input.onclick = innerEvent => innerEvent.stopPropagation();
            let finished = false;
            const finish = commit => {
                if (finished) return;
                finished = true;
                if (commit && renameLinkNode(node, input.value)) return;
                if (input.parentElement) input.replaceWith(titleElement);
            };
            input.onkeydown = keyEvent => {
                keyEvent.stopPropagation();
                if (keyEvent.key === 'Enter') {
                    keyEvent.preventDefault();
                    finish(true);
                } else if (keyEvent.key === 'Escape') {
                    keyEvent.preventDefault();
                    finish(false);
                }
            };
            input.onblur = () => finish(true);
            titleElement.replaceWith(input);
            input.focus();
            input.select();
        }

        function updateNodeName(oldName, newName) {
            if (selectedElement && selectedElement.type === 'link') {
                renameLinkNode(selectedElement.node, newName);
            }
        }
        function updateJointName(oldName, newName) {
            saveState();
            robotControllers().forEach(controller => {
                controller.joints = (controller.joints || []).map(
                    name => name === oldName ? newName : name
                );
            });
            selectedElement.jointObj.joint_name = newName;
            previewControlsDirty = true;
            render();
        }
        function updateJointType(jName, newType) {
            if (!selectedElement?.jointObj || selectedElement.jointObj.joint_name !== jName) return;
            saveState();
            const joint = selectedElement.jointObj;
            const jointInfo = joint.joint_info || {};
            joint.joint_info = jointInfo;

            // Changing only the URDF motion type must not discard a frame that
            // the user already picked in 3D.  In particular, keep the world
            // snap frame, its local xyz/rpy projection and the picked axis as
            // one unit while the preview controller is rebuilt.
            const pickedFrame = capturePickedJointFrame(jointInfo);
            joint.joint_type = newType;
            jointInfo.type = newType;
            if (newType === 'continuous') {
                delete jointInfo._manual_limit_lower_set;
                delete jointInfo._manual_limit_upper_set;
            }
            ensureJointMotionLimits(newType, jointInfo);
            restorePickedJointFrame(jointInfo, pickedFrame);
            if (!pickedFrame) jointInfo.provenance = 'user_tree_joint';

            previewRigDirty = true;
            previewControlsDirty = true;
            if (previewRigReady && robotRoot) {
                refreshPreviewRig();
                render({ skipPreview: true });
                updateSelectedJointFrameVisibility();
            } else {
                render();
            }
        }

        function activateSelectedJoint() {
            if (!selectedElement || selectedElement.type !== 'joint' || !selectedElement.jointObj) return;
            saveState();
            const joint = selectedElement.jointObj;
            joint.joint_info = joint.joint_info || {};
            joint.joint_info.provenance = 'user_tree_joint';
            previewRigDirty = true;
            previewControlsDirty = true;
            render();
        }

        function getPanelAxisType(axisValues) {
            const [x, y, z] = axisValues;
            if (x === 1 && y === 0 && z === 0) return 'x';
            if (x === -1 && y === 0 && z === 0) return 'nx';
            if (x === 0 && y === 1 && z === 0) return 'y';
            if (x === 0 && y === -1 && z === 0) return 'ny';
            if (x === 0 && y === 0 && z === 1) return 'z';
            if (x === 0 && y === 0 && z === -1) return 'nz';
            return 'custom';
        }

        function cloneJointSetting(value) {
            if (value === undefined) return undefined;
            return JSON.parse(JSON.stringify(value));
        }

        function capturePickedJointFrame(jointInfo) {
            if (!jointInfo) return null;
            const hasPickedFrame = jointInfo.provenance === 'user_3d_joint_pick'
                || jointInfo._joint_snap
                || (
                    Array.isArray(jointInfo._preview_world_frame_matrix)
                    && jointInfo._preview_world_frame_matrix.length === 16
                );
            if (!hasPickedFrame) return null;
            const snapshot = {};
            [
                'xyz', 'rpy', '_manual_rpy', 'axis', '_axis_source',
                '_preview_world_frame_matrix', '_preview_world_xyz',
                '_preview_world_quaternion', '_preview_local_quaternion',
                '_joint_snap', '_joint_mates', 'provenance'
            ].forEach(key => {
                if (jointInfo[key] !== undefined) {
                    snapshot[key] = cloneJointSetting(jointInfo[key]);
                }
            });
            return snapshot;
        }

        function restorePickedJointFrame(jointInfo, snapshot) {
            if (!jointInfo || !snapshot) return;
            Object.entries(snapshot).forEach(([key, value]) => {
                jointInfo[key] = cloneJointSetting(value);
            });
        }

        function ensureJointCadTransformSnapshot(jointInfo) {
            if (!jointInfo || jointInfo._cad_transform_snapshot) return;
            const snapshot = {};
            [
                'xyz', 'rpy', '_manual_rpy', '_joint_world_matrix',
                '_preview_world_frame_matrix', '_preview_world_xyz',
                '_preview_world_quaternion', '_preview_local_quaternion'
            ].forEach(key => {
                if (jointInfo[key] !== undefined) snapshot[key] = cloneJointSetting(jointInfo[key]);
            });
            jointInfo._cad_transform_snapshot = snapshot;
        }

        function optionalJointNumberValue(value) {
            return Number.isFinite(Number(value)) && value !== '' && value !== null
                ? Number(value) : '';
        }

        function updateJointXyzVal(jName, axisIndex, rawValue) {
            if (!selectedElement?.jointObj || selectedElement.jointObj.joint_name !== jName) return;
            const value = Number(rawValue);
            if (!Number.isFinite(value)) return;
            saveState();
            const jointInfo = selectedElement.jointObj.joint_info || {};
            selectedElement.jointObj.joint_info = jointInfo;
            ensureJointCadTransformSnapshot(jointInfo);
            const xyz = Array.isArray(jointInfo.xyz) ? jointInfo.xyz.slice() : [0, 0, 0];
            xyz[Number(axisIndex)] = value;
            jointInfo.xyz = xyz;
            delete jointInfo._joint_world_matrix;
            delete jointInfo._preview_world_frame_matrix;
            delete jointInfo._preview_world_xyz;
            jointInfo.provenance = 'user_joint_origin';
            previewRigDirty = true;
            render();
        }

        function restoreSelectedJointCadTransform() {
            if (!selectedElement?.jointObj) return;
            const jointInfo = selectedElement.jointObj.joint_info || {};
            const snapshot = jointInfo._cad_transform_snapshot;
            if (!snapshot) return;
            saveState();
            [
                'xyz', 'rpy', '_manual_rpy', '_joint_world_matrix',
                '_preview_world_frame_matrix', '_preview_world_xyz',
                '_preview_world_quaternion', '_preview_local_quaternion'
            ].forEach(key => delete jointInfo[key]);
            Object.entries(snapshot).forEach(([key, value]) => jointInfo[key] = cloneJointSetting(value));
            jointInfo.provenance = 'cad_transform_restored';
            previewRigDirty = true;
            render();
        }

        function updateOptionalJointNumber(field, input, positiveOnly = false, fallback = undefined) {
            if (!selectedElement?.jointObj || !input) return;
            const raw = String(input.value || '').trim();
            const jointInfo = selectedElement.jointObj.joint_info || {};
            let value = raw === '' ? fallback : Number(raw);
            const invalid = value !== undefined && (
                !Number.isFinite(value) || (positiveOnly ? value <= 0 : value < 0)
            );
            input.setCustomValidity(invalid ? (positiveOnly ? '0보다 큰 값을 입력하세요.' : '0 이상의 값을 입력하세요.') : '');
            if (invalid) return input.reportValidity();
            saveState();
            if (value === undefined) delete jointInfo[field];
            else jointInfo[field] = value;
            selectedElement.jointObj.joint_info = jointInfo;
            jointInfo.provenance = 'user_joint_properties';
            render({ skipPreview: true });
        }

        function updateSelectedJointTextValue(field, value) {
            if (!selectedElement?.jointObj) return;
            saveState();
            const jointInfo = selectedElement.jointObj.joint_info || {};
            selectedElement.jointObj.joint_info = jointInfo;
            if (value) jointInfo[field] = value;
            else delete jointInfo[field];
            jointInfo.provenance = 'user_joint_properties';
            render({ skipPreview: true });
        }

        function updateJointStateInterface(interfaceName, enabled) {
            if (!selectedElement?.jointObj) return;
            saveState();
            const jointInfo = selectedElement.jointObj.joint_info || {};
            const values = new Set(Array.isArray(jointInfo.state_interfaces)
                ? jointInfo.state_interfaces : ['position']);
            if (enabled) values.add(interfaceName);
            else values.delete(interfaceName);
            jointInfo.state_interfaces = ['position', 'velocity', 'effort'].filter(value => values.has(value));
            selectedElement.jointObj.joint_info = jointInfo;
            jointInfo.provenance = 'user_joint_control';
            render({ skipPreview: true });
        }

        function updateJointUrdfValue(jName, field, input) {
            if (!selectedElement || selectedElement.type !== 'joint' || !selectedElement.jointObj) {
                return false;
            }
            const joint = selectedElement.jointObj;
            if (joint.joint_name !== jName || !input) return false;
            const value = Number(input.value);
            const jointInfo = joint.joint_info || {};
            joint.joint_info = jointInfo;
            let error = '';
            if (!Number.isFinite(value)) {
                error = '숫자를 입력하세요.';
            } else if (['effort_limit', 'velocity_limit'].includes(field) && value <= 0) {
                error = '0보다 큰 값을 입력하세요.';
            } else if (
                field === 'lower_limit'
                && Number.isFinite(Number(jointInfo.upper_limit))
                && value >= Number(jointInfo.upper_limit)
            ) {
                error = '최소값은 최대값보다 작아야 합니다.';
            } else if (
                field === 'upper_limit'
                && Number.isFinite(Number(jointInfo.lower_limit))
                && value <= Number(jointInfo.lower_limit)
            ) {
                error = '최대값은 최소값보다 커야 합니다.';
            }
            input.setCustomValidity(error);
            if (error) {
                input.reportValidity();
                return false;
            }

            saveState();
            jointInfo[field] = value;
            jointInfo.provenance = 'user_tree_joint_parameters';
            if (field === 'lower_limit') jointInfo._manual_limit_lower_set = true;
            if (field === 'upper_limit') jointInfo._manual_limit_upper_set = true;
            const controller = previewJointControllers.find(item => (
                item.jointObj === joint || item.name === joint.joint_name
            ));
            if (controller) {
                if (field === 'lower_limit') controller.lowerLimit = value;
                if (field === 'upper_limit') controller.upperLimit = value;
            }
            previewControlsDirty = true;
            render();
            return true;
        }

        function updateJointAxisType(jName, type) {
            const joint = (selectedElement && selectedElement.jointObj && selectedElement.jointObj.joint_name === jName)
                ? selectedElement.jointObj
                : getFlatLinks(treeData, null, -1).map(item => item.jointObj).find(item => item && item.joint_name === jName);
            if (!joint) return;
            let axis = [0, 0, 1];
            if (type === 'x') axis = [1, 0, 0];
            else if (type === 'nx') axis = [-1, 0, 0];
            else if (type === 'y') axis = [0, 1, 0];
            else if (type === 'ny') axis = [0, -1, 0];
            else if (type === 'z') axis = [0, 0, 1];
            else if (type === 'nz') axis = [0, 0, -1];
            else axis = (joint.joint_info && joint.joint_info.axis) || [1, 0, 0];
            applyJointAxisChange(joint, axis, `user_axis_${type}`);
        }

        function updateJointAxisVal(jName, dim, val) {
            const joint = (selectedElement && selectedElement.jointObj && selectedElement.jointObj.joint_name === jName)
                ? selectedElement.jointObj
                : getFlatLinks(treeData, null, -1).map(item => item.jointObj).find(item => item && item.joint_name === jName);
            if (!joint) return;
            const axis = ((joint.joint_info && joint.joint_info.axis) || [0, 0, 1]).slice();
            if (dim === 'x') axis[0] = Number(val);
            else if (dim === 'y') axis[1] = Number(val);
            else if (dim === 'z') axis[2] = Number(val);
            applyJointAxisChange(joint, axis, 'user_custom_axis');
        }

        function updateJointAxisCandidate(jName, candidateIndex) {
            const joint = (selectedElement && selectedElement.jointObj && selectedElement.jointObj.joint_name === jName)
                ? selectedElement.jointObj
                : getFlatLinks(treeData, null, -1).map(item => item.jointObj).find(item => item && item.joint_name === jName);
            if (!joint || !joint.joint_info) return;
            const candidate = (joint.joint_info._axis_candidates || [])[Number(candidateIndex)];
            if (!candidate) return;
            applyJointAxisChange(joint, candidate.axis.slice(), candidate.label);
        }

        function updateJointRpyVal(jName, axisIndex, degrees) {
            if (!selectedElement || !selectedElement.jointObj || !Number.isFinite(Number(degrees))) return;
            saveState();
            const joint = selectedElement.jointObj;
            const jointInfo = joint.joint_info || {};
            joint.joint_info = jointInfo;
            ensureJointCadTransformSnapshot(jointInfo);
            const rpy = (jointInfo._manual_rpy || jointInfo.rpy || [0, 0, 0]).slice();
            rpy[Number(axisIndex)] = Number(degrees) * Math.PI / 180;
            jointInfo._manual_rpy = rpy;
            jointInfo.rpy = rpy;
            jointInfo._preview_local_quaternion = new THREE.Quaternion().setFromEuler(
                new THREE.Euler(rpy[0], rpy[1], rpy[2], 'ZYX')
            ).toArray();
            delete jointInfo._preview_world_quaternion;
            delete jointInfo._preview_world_frame_matrix;
            previewRigDirty = true;
            render();
        }

        let wizardFlatList = [];
        let wizardIndex = 0;
        let wizardCount = 1;

        function saveAndExit() {
            const graphValidation = validatePatcherGraph(true);
            const hasBlockingStructureProblem = (
                !graphValidation.worldConnected
                || graphValidation.disconnected.length > 0
                || graphValidation.incompleteLimits.length > 0
                || graphValidation.invalidLimits.length > 0
            );
            if (hasBlockingStructureProblem) {
                const vizPane = document.getElementById('viz-pane');
                if (vizPane) vizPane.scrollTo({ top: 0, behavior: 'smooth' });
                const status = document.getElementById('patcher-validation');
                if (status) {
                    const problems = [];
                    if (!graphValidation.worldConnected) {
                        problems.push('기준 프레임을 사용할 루트 링크에 연결하세요');
                    }
                    if (graphValidation.disconnected.length) {
                        problems.push(`미연결 링크 ${graphValidation.disconnected.length}개를 배선하거나 병합하세요`);
                    }
                    if (graphValidation.duplicates.length) {
                        problems.push(`중복 조인트 이름 ${graphValidation.duplicates.length}개를 수정하세요`);
                    }
                    if (graphValidation.incompleteLimits.length) {
                        problems.push(`회전 리밋 미완료 ${graphValidation.incompleteLimits.length}개의 최소·최대값을 모두 지정하세요`);
                    }
                    if (graphValidation.invalidLimits.length) {
                        problems.push(`리밋 오류 ${graphValidation.invalidLimits.length}개에서 lower를 upper보다 작게 설정하세요`);
                    }
                    status.textContent = `URDF 생성 전 ${problems.join(' · ')}`;
                }
                if (TREE_EDITOR_MODE) {
                    alert(
                        `아직 묶음 후보 ${graphValidation.disconnected.length}개가 남아 있습니다.\n`
                        + '같은 링크의 부품은 카드를 겹쳐 병합하고, 링크 사이 연결은 묶음 후보를 클릭해 실제 조인트로 전환하세요.'
                    );
                }
                return;
            }
            const proposedNames = buildStructureNamingPlan();
            const needsRename = !!proposedNames && (
                proposedNames.linkMappings.some(item => item.oldName !== item.newName)
                || proposedNames.jointMappings.some(item => item.oldName !== item.newName)
            );
            if (needsRename) {
                openStructureNamingAssistant(
                    true,
                    graphValidation.duplicates.length > 0
                );
            } else {
                proceedSave();
            }
        }

        function startRenameWizard() {
            document.getElementById('modal-container').style.display = 'none';
            wizardFlatList = getFlatLinks(treeData, null, -1).filter(
                item => isPatcherJointActive(item.jointObj)
            );
            wizardIndex = 0;
            wizardCount = 1;
            
            if (wizardFlatList.length > 0) {
                document.getElementById('rename-wizard').style.display = 'flex';
                showWizardStep();
            } else {
                proceedSave();
            }
        }

        function showWizardStep() {
            if (wizardIndex >= wizardFlatList.length) {
                closeRenameWizard();
                proceedSave();
                return;
            }

            const item = wizardFlatList[wizardIndex];
            const recommendedName = 'joint_' + wizardCount;
            
            document.getElementById('wizard-joint-name').innerText = recommendedName;
            
            // 트리에서 해당 조인트 하이라이트
            selectElement('joint', item.node, item.jointObj);
            
            // 트리 요소가 보이도록 스크롤 (옵션)
            const badges = document.querySelectorAll('.joint-badge');
            badges.forEach(b => {
                if (b.innerText.includes(item.jointObj.joint_name)) {
                    b.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
            });
        }

        function applyWizardRename() {
            saveState();
            const item = wizardFlatList[wizardIndex];
            item.jointObj.joint_name = 'joint_' + wizardCount;
            
            wizardIndex++;
            wizardCount++;
            showWizardStep();
        }

        function nextWizardStep() {
            wizardIndex++;
            wizardCount++; // 추천 번호는 건너뛰어도 증가시킴 (혹은 유지할지 선택 가능, 여기서는 증가)
            showWizardStep();
        }

        function closeRenameWizard() {
            document.getElementById('rename-wizard').style.display = 'none';
            selectedElement = null;
            highlight3DComponents([]);
            render();
        }

        function updateWslRvizStatus(message, isError = false) {
            const status = document.getElementById('wsl-rviz-status');
            if (!status) return;
            status.textContent = message;
            status.classList.toggle('error', isError);
        }

        async function pollWslRvizStatus() {
            try {
                const response = await fetch('/rviz/wsl/status');
                const data = await response.json();
                updateWslRvizStatus(data.message || 'WSL 상태를 확인하고 있습니다.');
                if (
                    data.status === 'preparing' ||
                    data.status === 'launching' ||
                    data.status === 'idle' ||
                    data.status === 'stopping'
                ) {
                    window.setTimeout(pollWslRvizStatus, 900);
                } else if (data.status === 'running') {
                    const button = document.getElementById('wsl-rviz-button');
                    if (button) button.textContent = 'RViz 실행 중';
                    const stopButton = document.getElementById('wsl-rviz-stop-button');
                    if (stopButton) stopButton.style.display = 'inline-block';
                } else if (data.status === 'stopped') {
                    const button = document.getElementById('wsl-rviz-button');
                    if (button) {
                        button.disabled = false;
                        button.textContent = 'RViz 다시 열기';
                    }
                    const stopButton = document.getElementById('wsl-rviz-stop-button');
                    if (stopButton) stopButton.style.display = 'none';
                } else if (data.status === 'error') {
                    updateWslRvizStatus(data.message || 'RViz 실행 실패', true);
                    const button = document.getElementById('wsl-rviz-button');
                    if (button) {
                        button.disabled = Boolean(data.process_running);
                        button.textContent = data.process_running ? 'RViz 종료 후 다시 열기' : 'RViz 다시 열기';
                    }
                    const stopButton = document.getElementById('wsl-rviz-stop-button');
                    if (stopButton) stopButton.style.display = data.process_running ? 'inline-block' : 'none';
                }
            } catch (error) {
                updateWslRvizStatus(`상태 확인 실패: ${error.message}`, true);
            }
        }

        async function startWslRviz() {
            const button = document.getElementById('wsl-rviz-button');
            if (button) {
                button.disabled = true;
                button.textContent = '동기화·빌드 중...';
            }
            updateWslRvizStatus('최신 ROS 2 패키지를 Ubuntu 22.04로 보내고 있습니다.');
            try {
                const response = await fetch('/rviz/wsl', {method: 'POST'});
                const data = await response.json();
                if (!response.ok) throw new Error(data.error || 'WSL RViz를 시작하지 못했습니다.');
                updateWslRvizStatus(data.message || 'WSL 빌드를 시작했습니다.');
                window.setTimeout(pollWslRvizStatus, 600);
            } catch (error) {
                updateWslRvizStatus(error.message, true);
                if (button) {
                    button.disabled = false;
                    button.textContent = 'RViz 다시 열기';
                }
            }
        }

        async function stopWslRviz() {
            updateWslRvizStatus('RViz와 ROS 2 표시 노드를 종료하고 있습니다.');
            try {
                const response = await fetch('/rviz/wsl/stop', {method: 'POST'});
                const data = await response.json();
                if (!response.ok) throw new Error(data.error || 'RViz를 종료하지 못했습니다.');
                updateWslRvizStatus(data.message || 'RViz가 종료되었습니다.');
                window.setTimeout(pollWslRvizStatus, 500);
            } catch (error) {
                updateWslRvizStatus(error.message, true);
            }
        }

        function updateWslMoveItStatus(message, isError = false) {
            const status = document.getElementById('wsl-moveit-status');
            if (!status) return;
            status.textContent = message;
            status.classList.toggle('error', isError);
        }

        function setMoveItButtonsBusy(busy) {
            const assistant = document.getElementById('wsl-moveit-assistant-button');
            const demo = document.getElementById('wsl-moveit-demo-button');
            if (assistant) assistant.disabled = busy;
            if (demo) demo.disabled = busy;
            const smoke = document.getElementById('wsl-moveit-smoke-button');
            if (smoke) smoke.disabled = true;
            const stop = document.getElementById('wsl-moveit-stop-button');
            if (stop) stop.style.display = busy ? 'inline-block' : 'none';
        }

        async function pollWslMoveItStatus() {
            try {
                const response = await fetch('/moveit/wsl/status');
                const data = await response.json();
                const isError = data.status === 'error';
                let message = data.message || 'MoveIt 상태 확인 중';
                if (isError && Array.isArray(data.output) && data.output.length) {
                    const lastLine = data.output[data.output.length - 1];
                    if (!lastLine.startsWith('PETASOS_')) {
                        message += ` · ${lastLine}`;
                    }
                }
                updateWslMoveItStatus(message, isError);
                const active = [
                    'preparing',
                    'stopping',
                    'assistant_running',
                    'demo_running'
                ].includes(data.status);
                setMoveItButtonsBusy(active);
                const smoke = document.getElementById('wsl-moveit-smoke-button');
                if (smoke) smoke.disabled = data.status !== 'demo_running';
                if (active) {
                    window.setTimeout(pollWslMoveItStatus, 900);
                }
            } catch (error) {
                setMoveItButtonsBusy(false);
                updateWslMoveItStatus(`MoveIt 상태 확인 실패: ${error.message}`, true);
            }
        }

        async function startWslMoveItAssistant() {
            setMoveItButtonsBusy(true);
            updateWslMoveItStatus(
                '페타소스 MoveIt 시작 설정을 검사하고 Setup Assistant를 열고 있습니다.'
            );
            try {
                const response = await fetch('/moveit/wsl/assistant', {method: 'POST'});
                const data = await response.json();
                if (!response.ok) {
                    throw new Error(data.error || 'MoveIt Setup Assistant를 열지 못했습니다.');
                }
                updateWslMoveItStatus(data.message || 'MoveIt Assistant 준비 중');
                window.setTimeout(pollWslMoveItStatus, 600);
            } catch (error) {
                setMoveItButtonsBusy(false);
                updateWslMoveItStatus(error.message, true);
            }
        }

        async function startWslMoveItDemo() {
            setMoveItButtonsBusy(true);
            updateWslMoveItStatus(
                'Assistant 저장 결과를 백업·정규화한 뒤 MoveIt 데모를 빌드하고 있습니다.'
            );
            try {
                const response = await fetch('/moveit/wsl/demo', {method: 'POST'});
                const data = await response.json();
                if (!response.ok) {
                    throw new Error(data.error || 'MoveIt 데모를 실행하지 못했습니다.');
                }
                updateWslMoveItStatus(data.message || 'MoveIt 데모 준비 중');
                window.setTimeout(pollWslMoveItStatus, 600);
            } catch (error) {
                setMoveItButtonsBusy(false);
                updateWslMoveItStatus(error.message, true);
            }
        }

        async function runWslMoveItSmoke() {
            const button = document.getElementById('wsl-moveit-smoke-button');
            if (button) button.disabled = true;
            updateWslMoveItStatus(
                '현재 관절 상태에서 안전한 작은 목표를 만들어 계획·실행하고 있습니다.'
            );
            try {
                const response = await fetch('/moveit/wsl/smoke', {method: 'POST'});
                const data = await response.json();
                if (!response.ok) {
                    throw new Error(data.error || 'MoveIt 움직임 검사에 실패했습니다.');
                }
                updateWslMoveItStatus(data.message || 'MoveIt 움직임 검사 성공');
                if (button) button.disabled = false;
            } catch (error) {
                if (button) button.disabled = false;
                updateWslMoveItStatus(error.message, true);
            }
        }

        async function stopWslMoveIt() {
            updateWslMoveItStatus('MoveIt 작업을 종료하고 있습니다.');
            try {
                const response = await fetch('/moveit/wsl/stop', {method: 'POST'});
                const data = await response.json();
                if (!response.ok) {
                    throw new Error(data.error || 'MoveIt 작업을 종료하지 못했습니다.');
                }
                updateWslMoveItStatus(data.message || 'MoveIt 작업을 종료했습니다.');
                window.setTimeout(pollWslMoveItStatus, 400);
            } catch (error) {
                updateWslMoveItStatus(error.message, true);
            }
        }

        let petasosRefreshCleanupStarted = false;
        let petasosRefreshCleanupFinished = false;

        async function cleanupWslGuiBeforeRefresh() {
            if (petasosRefreshCleanupStarted) return;
            petasosRefreshCleanupStarted = true;
            try {
                await fetch('/wsl/gui/stop', {
                    method: 'POST',
                    keepalive: true
                });
            } catch (_) {
                // The server-side cleanup can continue even if the page is closing.
            } finally {
                petasosRefreshCleanupFinished = true;
                window.location.reload();
            }
        }

        document.addEventListener('keydown', event => {
            const keyboardRefresh = event.key === 'F5' || (
                (event.ctrlKey || event.metaKey) &&
                event.key.toLowerCase() === 'r'
            );
            if (!keyboardRefresh) return;
            event.preventDefault();
            cleanupWslGuiBeforeRefresh();
        }, true);

        window.addEventListener('beforeunload', () => {
            if (petasosRefreshCleanupFinished) return;
            navigator.sendBeacon('/wsl/gui/stop');
        });

        function proceedSave() {
            const payload = {
                tree: treeData,
                fix_to_world: document.getElementById('fix-to-world').checked,
                root_joint_mode: rootJointMode(),
                include_moveit: document.getElementById('export-mode')?.value === 'moveit'
            };
            
            fetch('/save', {
                method: 'POST',
                body: JSON.stringify(payload),
                headers: {'Content-Type': 'application/json'}
            }).then(async r => {
                const data = await r.json();
                if (!r.ok) throw new Error(data.error || 'URDF 생성에 실패했습니다.');
                return data;
            }).then(data => {
                const sDir = data.bundle_dir || data.save_dir || "선택한 경로";
                if (treeData && treeData._standalone) {
                    fetch('/open-export-folder', { method: 'POST' }).catch(() => {});
                }
                const downloadButton = data.download_url
                    ? `<a href="${data.download_url}" class="result-button">ROS 2 패키지 다운로드</a>`
                    : '';
                const wslRvizButton = treeData && treeData._standalone
                    ? `<button id="wsl-rviz-button" class="result-button primary" onclick="startWslRviz()">RViz 열기</button>
                       <button id="wsl-rviz-stop-button" class="result-button danger" onclick="stopWslRviz()" style="display:none;">RViz 종료</button>`
                    : '';
                const wslMoveItButtons = treeData && treeData._standalone && data.include_moveit
                    ? `<section class="result-section">
                           <div class="result-section-heading">
                               <span class="result-section-number">2</span>
                               <div>
                                   <div class="result-section-title">MoveIt 설정 및 검사</div>
                                   <div class="result-section-subtitle">Assistant에서 설정한 뒤 같은 작업공간을 정규화하고 실제 움직임을 검사합니다.</div>
                               </div>
                           </div>
                           <div class="moveit-step-grid">
                               <button id="wsl-moveit-assistant-button" class="result-button" onclick="startWslMoveItAssistant()">1. Assistant 설정</button>
                               <button id="wsl-moveit-demo-button" class="result-button" onclick="startWslMoveItDemo()">2. 정규화·실행</button>
                               <button id="wsl-moveit-smoke-button" class="result-button" onclick="runWslMoveItSmoke()" disabled>3. 움직임 자동검사</button>
                           </div>
                           <div class="result-action-row" style="margin-top:9px;">
                               <button id="wsl-moveit-stop-button" class="result-button danger" onclick="stopWslMoveIt()" style="display:none;">MoveIt 종료</button>
                           </div>
                           <div id="wsl-moveit-status" class="result-status"></div>
                       </section>`
                    : '';
                const completionMessage = treeData && treeData._standalone
                    ? (data.include_moveit
                        ? 'description과 moveit_config가 start_petasos.cmd 옆 export/ros_ws/src에 생성되었습니다. Assistant가 이 작업공간을 직접 수정합니다.'
                        : 'MoveIt 없이 사용할 수 있는 ROS 2 기본 description 패키지가 생성되었습니다.')
                    : '이 브라우저 창을 닫고 Fusion 360으로 돌아가시면 생성이 진행됩니다.';
                document.body.innerHTML = `
                    <div class="export-result-page">
                        <main class="export-result-shell">
                            <header class="export-result-summary">
                                <div class="export-success-mark" aria-hidden="true">
                                    <svg viewBox="0 0 24 24">
                                        <path d="M5 12.5l4.2 4.2L19 7" fill="none" stroke="currentColor"
                                              stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
                                    </svg>
                                </div>
                                <div>
                                    <h1>URDF 생성이 완료되었습니다</h1>
                                    <p>${completionMessage}</p>
                                </div>
                            </header>
                            <section class="export-path-block">
                                <div class="export-path-label">저장 위치 · ROS 2 작업공간</div>
                                <div class="export-path-value">${sDir}</div>
                            </section>
                            <section class="result-section">
                                <div class="result-section-heading">
                                    <span class="result-section-number">1</span>
                                    <div>
                                        <div class="result-section-title">RViz에서 모델 확인</div>
                                        <div class="result-section-subtitle">Ubuntu 22.04 WSL로 최신 패키지를 동기화하고 RViz를 실행합니다.</div>
                                    </div>
                                </div>
                                <div class="result-action-row">${downloadButton}${wslRvizButton}</div>
                                <div id="wsl-rviz-status" class="result-status"></div>
                            </section>
                            ${wslMoveItButtons}
                        </main>
                    </div>`;
            }).catch(error => {
                alert(error.message);
            });
        }
    </script>
</body>
</html>
"""

class UIHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass

    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_CONTENT.encode('utf-8'))
        elif self.path == '/favicon.ico':
            self.send_response(204)
            self.end_headers()
        elif self.path == '/data':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(self.server.tree_data).encode('utf-8'))
        elif self.path.startswith('/static/three/'):
            try:
                filename = os.path.basename(urllib.parse.unquote(self.path))
                static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'vendor', 'three')
                filepath = os.path.join(static_dir, filename)
                if os.path.exists(filepath):
                    with open(filepath, 'rb') as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header('Content-type', 'application/javascript')
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self.send_response(404)
                    self.end_headers()
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                print("Static asset load error:", e)
        elif self.path.startswith('/meshes/'):
            try:
                filename = urllib.parse.unquote(self.path.split('/')[-1])
                filepath = os.path.join(self.server.save_dir, 'meshes', filename)
                if os.path.exists(filepath):
                    with open(filepath, 'rb') as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header('Content-type', 'application/sla')
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self.send_response(404)
                    self.end_headers()
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                print("STL Load Error:", e)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/save':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            self.server.saved_data = json.loads(post_data.decode('utf-8'))
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response_data = {"status": "ok", "save_dir": getattr(self.server, 'save_dir', 'Unknown')}
            self.wfile.write(json.dumps(response_data).encode('utf-8'))
            # Stop server
            threading.Thread(target=self.server.shutdown).start()

def show_ui_and_wait(tree_data, save_dir):
    class CustomServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
        daemon_threads = True

    server = CustomServer(('127.0.0.1', 0), UIHandler)
    port = server.server_address[1]
    server.tree_data = tree_data
    server.save_dir = save_dir
    server.saved_data = None

    # 서버를 별도의 스레드에서 실행하여 Fusion 360 메인 스레드를 막지 않음
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()

    # 브라우저 실행
    webbrowser.open(f'http://127.0.0.1:{port}')
    
    # 메인 스레드에서는 Fusion 360 UI가 응답 없음에 빠지지 않도록 adsk.doEvents() 호출하며 대기
    try:
        import adsk.core
        import time
        while server.saved_data is None:
            adsk.doEvents()
            time.sleep(0.1)
    except ImportError:
        # Fusion 360 환경이 아닐 경우를 대비한 일반 대기
        import time
        while server.saved_data is None:
            time.sleep(0.1)
            
    return server.saved_data
