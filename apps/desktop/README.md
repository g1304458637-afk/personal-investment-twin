# 投镜 Desktop UI Foundation

This directory contains the Tauri 2 + React + TypeScript desktop foundation for
Personal Investment Twin. The current application is an offline product UI
demonstration backed only by the fixed fixture in `src/demo/fixture.ts`.

It does not connect to a brokerage account, market-data service, model runtime,
or the Python financial engine. The Ask Twin panel is a presentation boundary
only, and the Decision Check returns values only for its one registered demo
scenario.

## Local development

Prerequisites: Node.js/npm and a Rust toolchain supported by Tauri 2.

```bash
npm install
npm run check
npm run dev
```

Open `http://127.0.0.1:1420/#/overview` for the browser preview. To run the
native shell:

```bash
npm run tauri dev
```

Production verification:

```bash
npm run build
npm run tauri -- build --no-bundle
```

The second command creates an unsigned local release binary without generating
platform installers. Distribution still requires the appropriate platform
signing and notarization work.

## Dependency and license boundary

Direct packages are locked in `package-lock.json`; Rust crates are locked in
`src-tauri/Cargo.lock`.

- Tauri: MIT OR Apache-2.0
- React, React Router, Radix UI, cmdk, Motion, Tailwind CSS, Vite, PostCSS,
  Autoprefixer, clsx and tailwind-merge: MIT
- Apache ECharts and TypeScript: Apache-2.0
- class-variance-authority: Apache-2.0
- Lucide: ISC

Jan, OpenPets, assistant-ui, Magic UI and Motion Primitives are source-study
references only. They are not dependencies, submodules, copied assets, or
vendored source in this application.
