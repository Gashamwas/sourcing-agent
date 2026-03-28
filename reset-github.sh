#!/bin/bash
# Reset GitHub sourcing agent for a fresh run.
# Usage: ./reset-github.sh

echo "Resetting GitHub sourcing agent..."

# Reset governor daily stats
echo '{"api_calls": [], "enrichments": [], "sessions_today": []}' > ~/.sourcing-governor/github/daily_stats.json
echo "  Governor stats cleared"

# Clear output files
rm -f output/github/*.jsonl output/github/progress.json output/github/saved_candidates.csv
echo "  Output files cleared"

echo "Done. Ready for a fresh run."
