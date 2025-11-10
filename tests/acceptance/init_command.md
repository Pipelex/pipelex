# Init Command - Acceptance Test Checklist

This document provides a comprehensive checklist for manually testing all scenarios of the `pipelex init` command.

## Pre-Test Setup

Before each test scenario, ensure:

- [ ] You have a clean test environment (consider using a temporary directory)
- [ ] No `.pipelex/` directory exists in your test location
- [ ] You have write permissions in the test directory

## Test Scenarios

### 1. First-Time Full Initialization (`pipelex init`)

**Test Case 1.1: Complete initialization with default selections**

- [ ] Run: `pipelex init`
- [ ] Verify welcome panel is displayed with list of actions
- [ ] Press Enter to confirm initialization
- [ ] Verify config files are copied successfully
- [ ] Verify backend selection panel is displayed with numbered options
- [ ] Select option `1` (pipelex_inference) and press Enter
- [ ] Verify confirmation message shows 1 backend configured
- [ ] Verify routing profile is set to "pipelex_first"
- [ ] Verify telemetry selection panel is displayed
- [ ] Select option `1` (OFF) and press Enter
- [ ] Verify telemetry mode is set successfully
- [ ] Verify `.pipelex/` directory exists with all config files
- [ ] Verify `.pipelex/inference/backends.toml` has pipelex_inference enabled
- [ ] Verify `.pipelex/inference/routing_profiles.toml` has active = "pipelex_first"
- [ ] Verify `.pipelex/telemetry.toml` has telemetry_mode = "off"

**Test Case 1.2: Initialization with multiple backends**

- [ ] Run: `pipelex init`
- [ ] Confirm initialization
- [ ] Note the displayed backend numbers, then select 3 backends (e.g., openai, anthropic, mistral) using their indices
- [ ] Verify confirmation shows 3 backends configured
- [ ] Verify "Setting up routing for multiple backends" message
- [ ] Verify primary backend selection panel is displayed
- [ ] Select primary backend (e.g., `1` for the first in your selection)
- [ ] Verify fallback order panel is displayed
- [ ] Press Enter to keep default order or enter custom order (e.g., `2,1`)
- [ ] Verify "custom_routing" profile is created and set as active
- [ ] Verify `.pipelex/inference/routing_profiles.toml` contains custom_routing profile
- [ ] Verify fallback_order is set correctly

**Test Case 1.3: Initialization with all backends**

- [ ] Run: `pipelex init`
- [ ] Confirm initialization
- [ ] Enter `a` or `all` for backend selection
- [ ] Verify all backends (except internal) are enabled
- [ ] Follow through routing and telemetry setup
- [ ] Verify all backends are enabled in backends.toml

**Test Case 1.4: Cancel at backend selection**

- [ ] Run: `pipelex init`
- [ ] Confirm initialization
- [ ] Enter `q` or `quit` at backend selection
- [ ] Verify graceful exit with message
- [ ] Verify config files were created but backends.toml remains in template state

**Test Case 1.5: Cancel at initialization confirmation**

- [ ] Run: `pipelex init`
- [ ] Enter `n` when asked to continue
- [ ] Verify cancellation message
- [ ] Verify suggestion to run `pipelex init` later
- [ ] Verify no files were created

---

### 2. Focused Initialization - Config Only

**Test Case 2.1: Initialize config files only**

- [ ] Run: `pipelex init config`
- [ ] Confirm initialization
- [ ] Verify config files are copied
- [ ] Verify NO backend selection prompt appears
- [ ] Verify NO telemetry prompt appears
- [ ] Verify `.pipelex/` directory exists with config files
- [ ] Verify `.pipelex/inference/backends.toml` exists in template state

**Test Case 2.2: Config already initialized**

- [ ] Run: `pipelex init config` (after already initialized)
- [ ] Verify message: "Configuration files are already in place!"
- [ ] Verify tip about using `--reset`
- [ ] Verify no changes made

---

### 3. Focused Initialization - Inference Only

**Test Case 3.1: Initialize inference with existing config**

- [ ] Ensure `.pipelex/` exists (run `pipelex init config` first)
- [ ] Run: `pipelex init inference`
- [ ] Verify backend selection panel is displayed
- [ ] Note the displayed backend numbers, then select 2 backends (e.g., openai, anthropic) using their indices
- [ ] Verify backends are enabled in backends.toml
- [ ] Verify routing is configured automatically
- [ ] Verify NO telemetry prompt appears

**Test Case 3.2: Initialize inference without config files**

- [ ] Remove `.pipelex/` directory
- [ ] Run: `pipelex init inference`
- [ ] Verify warning about missing backends.toml
- [ ] Verify command handles gracefully

**Test Case 3.3: Inference already configured**

- [ ] Run: `pipelex init inference` (after already configured)
- [ ] Verify message: "Inference backends are already configured!"
- [ ] Verify question: "Would you like to reconfigure inference backends?"
- [ ] Enter `y` to reconfigure
- [ ] Verify backend selection panel appears with current selection shown
- [ ] Verify you can change backends
- [ ] Verify routing is updated based on new selection

**Test Case 3.4: Decline reconfiguration**

- [ ] Run: `pipelex init inference` (after already configured)
- [ ] Enter `n` when asked to reconfigure
- [ ] Verify "No changes made" message
- [ ] Verify no changes to backends.toml

---

### 4. Focused Initialization - Routing Only

**Test Case 4.1: Configure routing with multiple backends enabled**

- [ ] Ensure `.pipelex/` exists with multiple backends enabled
- [ ] Run: `pipelex init routing`
- [ ] Verify primary backend selection panel
- [ ] Select primary backend
- [ ] Verify fallback order configuration
- [ ] Configure order and confirm
- [ ] Verify routing_profiles.toml is updated with custom_routing

**Test Case 4.2: Configure routing with single backend**

- [ ] Ensure only one backend is enabled
- [ ] Run: `pipelex init routing`
- [ ] Verify profile is set to `all_{backend_key}`
- [ ] Verify no primary/fallback prompts

**Test Case 4.3: Configure routing with no backends enabled**

- [ ] Disable all backends in backends.toml
- [ ] Run: `pipelex init routing`
- [ ] Verify warning: "No backends enabled. Please run 'pipelex init inference' first."
- [ ] Verify no changes to routing_profiles.toml

**Test Case 4.4: Routing already configured**

- [ ] Run: `pipelex init routing` (after already configured)
- [ ] Verify message: "Routing profile is already configured!"
- [ ] Verify question about reconfiguration
- [ ] Test both accepting and declining reconfiguration

---

### 5. Focused Initialization - Telemetry Only

**Test Case 5.1: Initialize telemetry only**

- [ ] Ensure `.pipelex/` exists without telemetry.toml
- [ ] Run: `pipelex init telemetry`
- [ ] Verify telemetry selection panel
- [ ] Select option `2` (ANONYMOUS)
- [ ] Verify telemetry.toml is created with mode = "anonymous"
- [ ] Verify NO backend or routing prompts

**Test Case 5.2: Telemetry already configured**

- [ ] Run: `pipelex init telemetry` (after already configured)
- [ ] Verify message: "Telemetry preferences are already configured!"
- [ ] Verify question about reconfiguration
- [ ] Enter `y` to reconfigure
- [ ] Select different mode
- [ ] Verify telemetry.toml is updated

**Test Case 5.3: Cancel telemetry selection**

- [ ] Run: `pipelex init telemetry`
- [ ] Enter `q` at telemetry prompt
- [ ] Verify graceful exit
- [ ] Verify telemetry.toml is not created

---

### 6. Reset Operations

**Test Case 6.1: Reset all with --reset**

- [ ] Ensure `.pipelex/` fully configured
- [ ] Run: `pipelex init --reset`
- [ ] Verify panel shows "Resetting Configuration" (yellow)
- [ ] Verify all items listed for reset
- [ ] Confirm reset
- [ ] Go through all selections again
- [ ] Verify all files are overwritten
- [ ] Verify new selections are applied

**Test Case 6.2: Reset config only**

- [ ] Run: `pipelex init config --reset`
- [ ] Verify config files are overwritten
- [ ] Verify backend selection prompt appears
- [ ] Complete configuration
- [ ] Verify backends.toml and routing are updated

**Test Case 6.3: Reset inference only**

- [ ] Run: `pipelex init inference --reset`
- [ ] Verify backend selection appears
- [ ] Change backend selection
- [ ] Verify backends.toml is updated
- [ ] Verify routing is reconfigured

**Test Case 6.4: Reset routing only**

- [ ] Run: `pipelex init routing --reset`
- [ ] Verify routing configuration prompts
- [ ] Change routing configuration
- [ ] Verify routing_profiles.toml is updated

**Test Case 6.5: Reset telemetry only**

- [ ] Run: `pipelex init telemetry --reset`
- [ ] Verify telemetry prompt
- [ ] Change telemetry mode
- [ ] Verify telemetry.toml is updated

---

### 7. All Already Configured

**Test Case 7.1: Everything configured**

- [ ] Ensure complete initialization
- [ ] Run: `pipelex init`
- [ ] Verify message: "Pipelex is already fully initialized!"
- [ ] Verify tip about `--reset`
- [ ] Verify no prompts appear
- [ ] Verify no changes made

---

### 8. Input Validation

**Test Case 8.1: Invalid backend selection - out of range**

- [ ] Run: `pipelex init`
- [ ] Enter invalid index like `99`
- [ ] Verify error message with valid range
- [ ] Verify prompt repeats
- [ ] Enter valid selection
- [ ] Verify successful continuation

**Test Case 8.2: Invalid backend selection - non-numeric**

- [ ] Run: `pipelex init`
- [ ] Enter invalid input like `abc`
- [ ] Verify error message
- [ ] Verify prompt repeats
- [ ] Enter valid selection

**Test Case 8.3: Space-separated backend indices**

- [ ] Run: `pipelex init`
- [ ] Note the displayed backend numbers, then enter 3 backend indices with spaces (e.g., for openai, anthropic, mistral)
- [ ] Verify backends are parsed correctly
- [ ] Verify all selected backends are enabled

**Test Case 8.4: Default selection (press Enter)**

- [ ] Run: `pipelex init`
- [ ] Press Enter at backend selection (accept default)
- [ ] Verify default backend (1 - pipelex_inference) is selected

**Test Case 8.5: Keep current selection**

- [ ] Run: `pipelex init inference` (with existing selection)
- [ ] Agree to reconfigure
- [ ] Press Enter at backend selection
- [ ] Verify current selection is kept

**Test Case 8.6: Invalid telemetry selection**

- [ ] Run: `pipelex init`
- [ ] Complete to telemetry prompt
- [ ] Enter invalid option like `5`
- [ ] Verify error message
- [ ] Enter valid option
- [ ] Verify successful completion

**Test Case 8.7: Invalid fallback order - wrong count**

- [ ] Select 3+ backends
- [ ] At fallback order prompt, enter only 2 indices
- [ ] Verify error: "You must specify all X backends"
- [ ] Enter correct count of indices
- [ ] Verify successful ordering

**Test Case 8.8: Invalid fallback order - duplicates**

- [ ] Select 3+ backends  
- [ ] At fallback order prompt, enter `1 1 2`
- [ ] Verify error: "Duplicate indices not allowed"
- [ ] Enter valid unique indices
- [ ] Verify successful ordering

---

### 9. Edge Cases

**Test Case 9.1: pipelex_inference always sets pipelex_first**

- [ ] Run: `pipelex init`
- [ ] Select pipelex_inference as one of multiple backends
- [ ] Verify routing is set to "pipelex_first" automatically
- [ ] Verify NO primary/fallback prompts

**Test Case 9.2: Single non-pipelex backend**

- [ ] Run: `pipelex init`
- [ ] Note the displayed backend numbers, then select only one backend (e.g., openai) using its index
- [ ] Verify routing is set to "all_{backend_key}" (e.g., "all_openai")
- [ ] Verify profile is created if it doesn't exist
- [ ] Verify NO primary/fallback prompts

**Test Case 9.3: Profile creation confirmation**

- [ ] Select a single obscure backend
- [ ] If profile doesn't exist in template, verify prompt to create
- [ ] Accept profile creation
- [ ] Verify profile is created in routing_profiles.toml

**Test Case 9.4: Decline profile creation**

- [ ] Select a backend without existing profile
- [ ] Decline profile creation when prompted
- [ ] Verify message: "Keeping current routing profile configuration"
- [ ] Verify no changes to routing_profiles.toml

**Test Case 9.5: Two backends (automatic fallback)**

- [ ] Select exactly 2 backends
- [ ] Select primary backend
- [ ] Verify fallback_order is set automatically with both backends
- [ ] Verify NO fallback ordering prompt (only 1 remaining)

---

### 10. Files and Directory Structure

**Test Case 10.1: Verify directory structure**

After complete initialization, verify:

- [ ] `.pipelex/` directory exists
- [ ] `.pipelex/pipelex.toml` exists
- [ ] `.pipelex/inference/` directory exists
- [ ] `.pipelex/inference/backends.toml` exists
- [ ] `.pipelex/inference/routing_profiles.toml` exists
- [ ] `.pipelex/telemetry.toml` exists
- [ ] All other expected config files from template are present

**Test Case 10.2: Verify file contents - backends.toml**

- [ ] Open `.pipelex/inference/backends.toml`
- [ ] Verify selected backends have `enabled = true`
- [ ] Verify non-selected backends have `enabled = false`
- [ ] Verify `internal` backend is always enabled

**Test Case 10.3: Verify file contents - routing_profiles.toml**

- [ ] Open `.pipelex/inference/routing_profiles.toml`
- [ ] Verify `active` field matches expected profile
- [ ] If custom_routing: verify `default` and `fallback_order` fields
- [ ] Verify `routes` section exists

**Test Case 10.4: Verify file contents - telemetry.toml**

- [ ] Open `.pipelex/telemetry.toml`
- [ ] Verify `telemetry_mode` matches selection
- [ ] Verify valid values: "off", "anonymous", or "identified"

**Test Case 10.5: Existing files not overwritten (without reset)**

- [ ] Modify `.pipelex/pipelex.toml` (add a comment)
- [ ] Run: `pipelex init config`
- [ ] Verify your comment is preserved
- [ ] Verify message about skipped existing files

---

### 11. Doctor Integration

**Test Case 11.1: Doctor command suggests init**

- [ ] Remove `.pipelex/` directory
- [ ] Run: `pipelex doctor`
- [ ] Verify doctor detects missing configuration
- [ ] Follow suggestion to run init
- [ ] Verify successful configuration

---

### 12. Performance and UX

**Test Case 12.1: Responsive feedback**

- [ ] Run: `pipelex init`
- [ ] Verify all prompts appear immediately
- [ ] Verify success messages appear after actions
- [ ] Verify progress is clear at each step

**Test Case 12.2: Clear instructions**

- [ ] Run through full initialization
- [ ] Verify all panels have clear titles
- [ ] Verify all prompts have clear instructions
- [ ] Verify examples are provided (e.g., "1,5,6 or 1 5 6")
- [ ] Verify default values are clearly indicated

**Test Case 12.3: Error recovery**

- [ ] Make intentional errors at each prompt
- [ ] Verify error messages are helpful
- [ ] Verify you can recover and continue
- [ ] Verify no need to restart from beginning

---

## Test Environment Cleanup

After completing tests:

- [ ] Remove test `.pipelex/` directories
- [ ] Document any issues found
- [ ] Note any unclear UX or confusing prompts
- [ ] Record any unexpected behavior

---

## Sign-Off

**Tester Name:** _________________________

**Date:** _________________________

**Test Environment:**

- OS: _________________________
- Python Version: _________________________
- Pipelex Version: _________________________

**Overall Result:** [ ] PASS [ ] FAIL

**Notes:**

_____________________________________________________________________________

_____________________________________________________________________________

_____________________________________________________________________________

