# G10 editor (React Flow) + G9 Matryoshka

Greenfield Vite + React + `@xyflow/react` canvas for guest-dsl. Matches dsl-gui *feel* (pan/zoom/connect/multi-select, undo/redo, minimap, auto-layout, light theme) and dsl-gui-v2 Matryoshka nested-scope *intention* (compound expand/collapse + drill-in). G8 ChatPanel overlays the canvas (SSE `/v0/chat`, tools mutate the live graph). **Not** a code lift of getafix-seed-paul `dsl-gui`.

The guest stays runnable without npm. `platform_run.py` serves the committed bundle in `ui/` (`/ui/app.js`, `/ui/app.css`, `/ui/index.html`). Files browse (`files.html` / `files.js`) is unchanged vanilla.

## Build / serve

```bash
# from the guest root — stdlib only, no npm
python3 ./platform_run.py
# open http://127.0.0.1:18380/
```

Rebuild the committed bundle after editing `editor/src/`:

```bash
cd editor
npm install
npm test          # history / layout / persist / graph (node:test)
npm run build     # writes ../ui/index.html, ../ui/app.js, ../ui/app.css
```

Optional live reload (proxy `/v0` to the guest):

```bash
python3 ./platform_run.py          # :18380
cd editor && npm run dev           # :5173
```

Do not commit `editor/node_modules`. Do commit the rebuilt `ui/app.js` / `ui/app.css` / `ui/index.html` so emulate / `python3 ./platform_run.py` keep working without a frontend toolchain.
