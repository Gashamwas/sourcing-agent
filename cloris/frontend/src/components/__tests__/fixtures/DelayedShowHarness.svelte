<!--
  DelayedShowHarness — minimal test fixture for lib/minDisplay.svelte.ts.

  Mirrors StickyHarness but for the inverse utility (useDelayedShow):
  wait delayMs after pending() flips true; if still true at boundary,
  show; if pending flipped false, never show.

  Tests render the harness, flip the `pending` prop, advance fake
  timers across the delayMs boundary, and assert against
  data-show on the rendered output.
-->
<script lang="ts">
  import { useDelayedShow } from "../../../lib/minDisplay.svelte";

  let { pending, delayMs }: { pending: boolean; delayMs: number } = $props();

  // svelte-ignore state_referenced_locally
  const show = useDelayedShow(
    () => pending,
    () => delayMs
  );
</script>

<div data-testid="delayed" data-show={show() ? "true" : "false"}>
  {show() ? "show-true" : "show-false"}
</div>
