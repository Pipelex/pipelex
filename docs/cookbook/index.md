---
title: "The Pipelex Cookbook"
description: "The Pipelex Cookbook holds Pipelex's example methods, each one runnable by its address on the hosted Pipelex API, with a page showing every way to use it."
---

# The Pipelex Cookbook

[![GitHub](https://img.shields.io/badge/Cookbook_Repository-5a0dad?logo=github&logoColor=white&style=flat)](https://github.com/Pipelex/pipelex-cookbook)

The [Pipelex Cookbook](https://github.com/Pipelex/pipelex-cookbook) holds Pipelex's example methods. Each one is a package that runs by its address on the hosted Pipelex API, such as `github.com/Pipelex/pipelex-cookbook/extract_gantt@v0.19.0`, so there is nothing to clone and nothing to install before you try it.

Every method has its own page in the cookbook, and every page shows the same ways to use it: in your chatbot through the Pipelex MCP, in your coding agent through the Pipelex plugin, in your code through the TypeScript or Python SDK or over HTTP, as a web app made from the method-app template, and how to make it yours by copying it, changing it and saving it to your account. The [list of methods](https://github.com/Pipelex/pipelex-cookbook#methods-you-can-run-by-address) on the cookbook's front page links to each page, and the page for [Gantt chart extraction](https://github.com/Pipelex/pipelex-cookbook/tree/main/methods/extract_gantt) is a good one to start with.

The cookbook also has [recipes](https://github.com/Pipelex/pipelex-cookbook/tree/main/recipes), each of which takes one way of using a method further on a real case, such as a FastAPI endpoint, a Next.js server action or a web app you deploy. Its [tutorial](https://github.com/Pipelex/pipelex-cookbook/tree/main/tutorial) teaches you to write methods in MTHDS by hand and to run them on your own machine.

The methods Pipelex publishes as reusable building blocks, such as invoice extraction and table extraction, live in the [method library](https://github.com/Pipelex/methods) instead, and they run by their address in the same way.

This documentation explains each part of Pipelex once, as a reference, and the cookbook shows each of them working on a real method. If you have not used Pipelex yet, the [Quick Start](../get-started/quick-start.md) sets up the Pipelex plugin and the Pipelex MCP that the cookbook's pages rely on.
