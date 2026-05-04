<!--
  Test fixture: a child that always renders successfully. Used to verify
  the ErrorBoundary's pass-through path and to mount a non-throwing child
  while we observe lifecycle side effects (unhandledrejection listener
  attach/detach).
-->
<script lang="ts">
  // Intentionally empty — the marker test-id is enough.
</script>

<div data-testid="ok-child">child rendered fine</div>
