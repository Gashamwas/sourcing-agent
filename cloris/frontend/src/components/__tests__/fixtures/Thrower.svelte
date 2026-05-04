<!--
  Test fixture: a component that always throws synchronously during
  initial render. The throw runs during component instantiation, which
  is inside the parent boundary's reactive scope and therefore caught
  by <svelte:boundary>.

  The "state_referenced_locally" warning is expected — by design the
  prop is read once and immediately thrown. We silence it because it's
  noise specific to this fixture.
-->
<script lang="ts">
  let { message = "boom" } = $props<{ message?: string }>();
  // svelte-ignore state_referenced_locally
  throw new Error(message);
</script>
