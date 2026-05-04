<script lang="ts">
  // Test harness for SpecimenFrame. Svelte 5 snippets cannot be passed
  // directly through @testing-library/svelte's render() ergonomically,
  // so this harness wraps SpecimenFrame with a hard-coded child that
  // tests can assert against. Props pass-through to SpecimenFrame.

  import SpecimenFrame from "../SpecimenFrame.svelte";

  let {
    label,
    footnote = null,
    tag = null
  }: {
    label: string;
    footnote?: string | null;
    tag?: string | null;
  } = $props();
</script>

<SpecimenFrame {label} {footnote} {tag}>
  <div data-testid="frame-children">test child content</div>
</SpecimenFrame>
