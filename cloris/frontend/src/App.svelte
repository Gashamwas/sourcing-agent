<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { refreshStatus } from "./lib/stores";
  import AmbientBanner from "./components/AmbientBanner.svelte";
  import LaunchForm from "./components/LaunchForm.svelte";
  import StateDirList from "./components/StateDirList.svelte";

  // Three-second polling cadence with visibility-aware pause/resume:
  //   - mount: poll once, then start the interval.
  //   - tab hidden: clear the interval; do not poll while invisible.
  //   - tab visible: refresh once immediately and restart the interval.
  //   - destroy: clear interval and remove the visibility listener.
  // The cadence is intentionally generous — the Cloris control plane is
  // not a real-time dashboard.
  const POLL_MS = 3000;
  let timer: ReturnType<typeof setInterval> | null = null;

  function startPolling() {
    if (timer !== null) return;
    timer = setInterval(refreshStatus, POLL_MS);
  }

  function stopPolling() {
    if (timer === null) return;
    clearInterval(timer);
    timer = null;
  }

  function onVisibilityChange() {
    if (document.visibilityState === "hidden") {
      stopPolling();
    } else {
      refreshStatus();
      startPolling();
    }
  }

  onMount(() => {
    refreshStatus();
    startPolling();
    document.addEventListener("visibilitychange", onVisibilityChange);
  });

  onDestroy(() => {
    stopPolling();
    if (typeof document !== "undefined") {
      document.removeEventListener("visibilitychange", onVisibilityChange);
    }
  });
</script>

<main>
  <AmbientBanner />
  <LaunchForm />
  <StateDirList />
</main>
