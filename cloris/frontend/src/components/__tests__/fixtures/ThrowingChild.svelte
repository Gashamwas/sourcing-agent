<!--
  Test fixture: wraps the real ErrorBoundary around a child that throws
  during the initial render (via $effect.pre, which runs before render
  but inside reactive setup so the boundary's onerror catches it).

  Why a wrapper exists at all: rendering a throwing component directly
  bubbles the error past @testing-library before our boundary mounts.
  Instead, the test renders this wrapper, which mounts the boundary
  first and then triggers the descendant throw inside it.
-->
<script lang="ts">
  import ErrorBoundary from "../../ErrorBoundary.svelte";
  import Thrower from "./Thrower.svelte";

  let { message = "boom from descendant" }: { message?: string } = $props();
</script>

<ErrorBoundary>
  <Thrower {message} />
</ErrorBoundary>
