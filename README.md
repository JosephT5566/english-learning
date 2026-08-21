# sv

Everything you need to build a Svelte project, powered by [`sv`](https://github.com/sveltejs/cli).

## Full-stack training

This application is being evolved into a multilingual full-stack product with a Python backend and PostgreSQL. See the [training documentation](doc/training/README.md) for the roadmap, current project memory, weekly logs, architecture decisions, and verified engineering evidence.

## Creating a project

If you're seeing this, you've probably already done this step. Congrats!

```sh
# create a new project in the current directory
npx sv create

# create a new project in my-app
npx sv create my-app
```

## Developing

Once you've created a project and installed dependencies with `npm install` (or `pnpm install` or `yarn`), start a development server:

```sh
npm run dev

# or start the server and open the app in a new browser tab
npm run dev -- --open
```

## Building

To create a production version of your app:

```sh
npm run build
```

You can preview the production build with `npm run preview`.

> To deploy your app, you may need to install an [adapter](https://svelte.dev/docs/kit/adapters) for your target environment.

## GitHub Page

We can refer to the guide for the setting.
https://svelte.dev/docs/kit/adapter-static#GitHub-Pages
