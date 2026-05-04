// Surface-level Svelte transitions for loader → content swaps.
//
// Why this file exists: Svelte's built-in `fade` doesn't honor
// `prefers-reduced-motion`, and the bare `{#if loading}{:else}{/if}`
// pattern flips DOM instantly which reads as a hard cut. These helpers
// wrap `svelte/transition.fade` with reduced-motion guards and a
// loader-out / content-in pair that's tuned for editorial pacing.
//
// The default cadence:
//   - loader fades out over 220ms
//   - content fades in over 320ms with a 140ms delay
// Net: ~460ms of softness, ~80ms of overlap (so the swap reads as a
// natural cross-dissolve rather than blink-replace).
//
// Reduced-motion: returns { duration: 0, delay: 0 } — both elements
// flip instantly with no fade, matching how the existing CSS animations
// degrade under the same media query (components.css:6428-6452).

import { fade as svelteFade, fly as svelteFly } from "svelte/transition";
import type {
  FadeParams,
  FlyParams,
  TransitionConfig,
} from "svelte/transition";
import { cubicOut } from "svelte/easing";

const LOADER_FADE_OUT_MS = 220;
const SURFACE_FADE_IN_MS = 320;
const SURFACE_FADE_IN_DELAY_MS = 140;
const ROW_FLY_IN_MS = 380;
const ROW_FLY_IN_OFFSET_PX = -16;

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return false;
  if (typeof window.matchMedia !== "function") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

// Web Animations API guard. JSDom (test env) doesn't implement
// `Element.prototype.animate`, which `svelte/transition.fade` calls
// internally. Treating "no animate" the same as reduced-motion lets
// the same code path run under tests without try/catch noise.
function hasAnimateAPI(): boolean {
  if (typeof Element === "undefined") return false;
  return typeof Element.prototype.animate === "function";
}

function shouldSkipMotion(): boolean {
  return prefersReducedMotion() || !hasAnimateAPI();
}

// Use as `out:loaderFadeOut` on the loader-branch element.
export function loaderFadeOut(
  node: Element,
  params: FadeParams = {},
): TransitionConfig {
  if (shouldSkipMotion()) return { duration: 0 };
  return svelteFade(node, {
    duration: params.duration ?? LOADER_FADE_OUT_MS,
    delay: params.delay,
    easing: params.easing,
  });
}

// Use as `in:surfaceFadeIn` on the content-branch element.
export function surfaceFadeIn(
  node: Element,
  params: FadeParams = {},
): TransitionConfig {
  if (shouldSkipMotion()) return { duration: 0, delay: 0 };
  return svelteFade(node, {
    duration: params.duration ?? SURFACE_FADE_IN_MS,
    delay: params.delay ?? SURFACE_FADE_IN_DELAY_MS,
    easing: params.easing,
  });
}

// Use as `in:rowFlyIn|local` on a card row inside a list, so a new
// card landing in the homescreen Needs Attention stack reads as a
// gentle drop from above (toward the recruiter's last action — the
// LaunchForm sits directly above the card stack). The `|local`
// modifier means it only fires on list mutation, not on the page's
// initial mount.
export function rowFlyIn(
  node: Element,
  params: FlyParams = {},
): TransitionConfig {
  if (shouldSkipMotion()) return { duration: 0 };
  return svelteFly(node, {
    y: params.y ?? ROW_FLY_IN_OFFSET_PX,
    duration: params.duration ?? ROW_FLY_IN_MS,
    easing: params.easing ?? cubicOut,
    delay: params.delay,
  });
}
