<!--
  Test fixture: ErrorBoundary wrapping a non-throwing child. Mirrors
  ThrowingChild's structure so tests can render either path with the
  same shape.
-->
<script lang="ts">
  import ErrorBoundary from "../../ErrorBoundary.svelte";
  import OkChild from "./OkChild.svelte";
</script>

<ErrorBoundary>
  <OkChild />
</ErrorBoundary>
