<script lang="ts">
  // StickyHarness — minimal test fixture for lib/minDisplay.svelte.ts.
  //
  // The stickyTrue helper uses Svelte 5 runes ($state, $effect), which
  // only execute inside a Svelte component context. This fixture wraps
  // the helper so a .test.ts file can render it, flip the `source` prop,
  // and assert against the rendered sticky value (via the data-sticky
  // attribute the test reads with getAttribute).

  import { stickyTrue } from "../../../lib/minDisplay.svelte";

  let { source, minMs }: { source: boolean; minMs: number } = $props();

  // Wrap the prop in a getter so the rune source closes over the live
  // value. minMs is intentionally captured at mount time — tests that
  // need different boundaries re-render with a different fixture.
  // svelte-ignore state_referenced_locally
  const sticky = stickyTrue(() => source, minMs);
</script>

<div data-testid="sticky" data-sticky={sticky() ? "true" : "false"}>
  {sticky() ? "sticky-true" : "sticky-false"}
</div>
