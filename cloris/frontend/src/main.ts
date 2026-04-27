import { mount } from "svelte";
import App from "./App.svelte";

import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/components.css";

const target = document.getElementById("cloris-shell");
if (!target) {
  throw new Error("cloris: missing #cloris-shell mount point in index.html");
}

mount(App, { target });
