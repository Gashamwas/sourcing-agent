<script lang="ts">
  // PageBackLink — the navigation primitive that returns the user to a
  // parent surface (typically `#/`). Sits at the top of any non-home
  // page (run report, filed, onboarding, 404) in its own breathing
  // strip, deliberately separated from the main content card so it
  // reads as page chrome — not as part of the editorial body.
  //
  // Why a dedicated primitive: the previous treatment reused
  // `.homescreen-look-through` for both forward-nav ("View paused
  // briefs" at the bottom of the homescreen) and back-nav ("Back to
  // home" at the top of every other page). They have different
  // semantics and different positional needs — back-nav wants visual
  // distance from the next content card; forward-nav lives inline
  // with related content. Splitting the primitive keeps the styling
  // and positioning of each independently tunable.
  //
  // Visual contract: small mono-caps text + leading "←" chevron, colour
  // ink-meta with a peach-deep accent on the chevron. Hovers shift the
  // chevron 2px left, the standard "follow me" affordance.

  let {
    href = "#/",
    label = "Back to home",
  }: {
    href?: string;
    label?: string;
  } = $props();
</script>

<div class="page-back-strip">
  <a class="page-back-link" {href}>
    <span class="page-back-link-chevron" aria-hidden="true">&larr;</span>
    <span class="page-back-link-label">{label}</span>
  </a>
</div>
