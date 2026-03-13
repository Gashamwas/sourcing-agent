"""Human-like timing distributions for browser automation.

Human inter-event times follow log-normal distributions (heavy-tailed:
mostly quick, occasionally slow) with temporal autocorrelation (consecutive
delays are correlated). Uniform random delays are detectable by entropy-based
classifiers with near-100% accuracy.

Usage:
    from human_timing import human_delay, human_delay_correlated

    await asyncio.sleep(human_delay(1.5, 4.0))        # single delay
    await asyncio.sleep(human_delay_correlated(2.0))   # session-correlated
"""

import math
import random

# Log-normal parameters (per deep research: μ≈1.5, σ≈0.8 for inter-action delays)
# These produce a median of ~4.5s with a long tail up to ~30s.
# For shorter actions we scale down.
_DEFAULT_MU = 1.5
_DEFAULT_SIGMA = 0.8

# State for correlated delays (consecutive delays should be correlated, not independent)
_last_delay: float = 0.0
_CORRELATION_WEIGHT = 0.3  # How much the previous delay influences the next


def human_delay(low: float, high: float, mu: float = 0.0, sigma: float = 0.6) -> float:
    """Sample a log-normal delay, clamped to [low, high].

    If mu is 0, it's auto-calculated to center the distribution's median
    at the midpoint of [low, high].
    """
    if mu == 0:
        # Set mu so median = midpoint of range
        midpoint = (low + high) / 2.0
        mu = math.log(max(midpoint, 0.1))

    sample = random.lognormvariate(mu, sigma)
    return max(low, min(high, sample))


def human_delay_correlated(base: float, spread: float = 0.6) -> float:
    """Sample a delay with temporal autocorrelation.

    Consecutive calls produce correlated values — a long pause makes the
    next pause slightly longer, and vice versa. This matches human behavior
    where attention shifts produce clustered timing.

    base: center of the delay range
    spread: log-normal sigma (higher = more variance)
    """
    global _last_delay

    mu = math.log(max(base, 0.1))
    raw = random.lognormvariate(mu, spread)

    # Blend with previous delay for autocorrelation
    if _last_delay > 0:
        blended = (1 - _CORRELATION_WEIGHT) * raw + _CORRELATION_WEIGHT * _last_delay
    else:
        blended = raw

    # Clamp to reasonable bounds (0.3x to 4x the base)
    result = max(base * 0.3, min(base * 4.0, blended))
    _last_delay = result
    return result
