# Apple Developer setup runbook (human action required)

This is the prerequisite checklist for Phase 2 (code signing +
notarization) of the Cloris .app build. Most steps below are
out-of-band actions on Apple's website; the schedule risk is
unpredictable (Apple's enrollment verification can be hours or a
week — see plan §6).

**Start this on day 1 of the packaging project, in parallel with
Phase 0 engineering work.** Do not wait until you've got a built
.app and discover the cert isn't ready.

## Cost

- Apple Developer Program: $99/year (individual) or $99/year
  (organization, requires D-U-N-S number).

## Decision: individual vs organization account

If Cloris will distribute under "Cloris" (the project / company
brand), enroll as an organization account — the developer ID
embedded in the signed binary will read as the organization name,
which is what A24's IT will see during their review.

Individual accounts work fine for trial-day distribution but the
developer ID will read as the developer's personal name (e.g.
"Sam Vangelos") which can look unprofessional on a marquee
customer's machine.

## Step-by-step

### 1. Enroll in the Apple Developer Program

URL: https://developer.apple.com/programs/enroll/

For an organization account, Apple requires:
- A D-U-N-S Number (free, 1–5 business days to obtain at
  https://developer.apple.com/support/D-U-N-S/)
- Legal entity name match between the account and the D-U-N-S record
- Authority to sign legal agreements

For an individual account, Apple requires:
- An Apple ID (free)
- Two-factor authentication enabled
- Acceptance of the Apple Developer Agreement

**Verification window: 1 hour to 2 weeks. Plan for 5–7 days.**

### 2. Create a Developer ID Application certificate

Once enrolled:

1. Open Xcode → Settings → Accounts (or "Preferences" on older Xcode).
2. Add the Apple ID associated with the Developer Program.
3. Click "Manage Certificates..." → "+" → "Developer ID Application".
4. Xcode generates the cert + private key in the local keychain.

**The cert lives only in the keychain it was generated in.** If you
build on a different Mac, you must export the cert + private key
(.p12 file) from the original keychain and import on the build Mac.
Lose the key and you can never re-sign existing certificates — you'd
need to revoke and create a new one.

### 3. Create an app-specific password for `notarytool`

`notarytool` (the modern notarization CLI) authenticates with your
Apple ID + an app-specific password (NOT your real Apple ID
password).

1. Visit https://appleid.apple.com → Sign in.
2. Sign-In and Security → App-Specific Passwords → Generate.
3. Label: "Cloris notarytool". Save the generated password somewhere
   secure (you cannot view it again).

Alternative: store credentials in the keychain via
`xcrun notarytool store-credentials --apple-id <email> --team-id
<TEAM> --password <app-specific>`. This caches them under a
profile name (e.g. "cloris-notary") so subsequent submissions
skip the inline auth args. Recommended for repeated builds.

### 4. Find your Team ID

The Team ID is a 10-character alphanumeric Apple uses to identify
your developer account on the notary side.

1. Visit https://developer.apple.com/account/.
2. Membership Details → Team ID is on the right.
3. Save it; you'll need it for every `notarytool submit` call.

### 5. Smoke-test the cert

Before building Cloris, verify the cert works on a trivial binary:

```bash
echo 'int main(){return 0;}' > /tmp/t.c
clang /tmp/t.c -o /tmp/t
codesign --sign "Developer ID Application: <Your Name> (<TEAM>)" \
    --timestamp \
    --options runtime \
    /tmp/t
codesign -dv --verbose=4 /tmp/t
```

The `codesign -dv` output should show your developer ID and
"Authority=Apple Worldwide Developer Relations Certification
Authority". If it errors with "no identity found", the cert is not
in the keychain or has expired.

### 6. Set environment variables for the build scripts

The Cloris signing + notarization scripts read these env vars.
Set them in `~/.zshrc` (or wherever your shell init lives):

```bash
# Required for sign-app.sh and notarize-app.sh.
export CLORIS_SIGN_IDENTITY="Developer ID Application: Your Org Name (TEAMID1234)"
export CLORIS_APPLE_ID="your-apple-id@example.com"
export CLORIS_TEAM_ID="TEAMID1234"
export CLORIS_NOTARY_PROFILE="cloris-notary"  # if you used store-credentials
```

If you stored credentials via `notarytool store-credentials`, the
notarize script uses `--keychain-profile $CLORIS_NOTARY_PROFILE`
and ignores `CLORIS_APPLE_ID` / app-specific password env vars.

## Verification before build

Run before invoking `build-app.sh`:

```bash
# Cert in keychain?
security find-identity -p codesigning -v | grep "Developer ID Application"

# Notary credentials cached?
xcrun notarytool history --keychain-profile $CLORIS_NOTARY_PROFILE | head -5
```

Both should succeed. If either fails, fix the underlying issue
before proceeding — the build pipeline will not work without them.

## Hard limits to be aware of

- Apple ID password changes invalidate app-specific passwords.
  Re-generate after any Apple ID password change.
- Developer ID Application certificates expire after 5 years. They
  can be renewed; existing notarized binaries continue to validate
  via the embedded notarization ticket even after the cert expires.
- The notary service has rate limits — practical concurrency is
  ~1 submission at a time per developer account; the response
  window is typically minutes but can stretch to ~1 hour during
  Apple infrastructure incidents.
- Notarization requires hardened runtime — see the entitlements
  configured in `cloris/packaging/entitlements.plist` and the
  signing semantics owned by `cloris/packaging/scripts/sign-app.sh`.
