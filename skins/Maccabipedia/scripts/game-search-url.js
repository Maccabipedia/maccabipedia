/* Drop empty fields from the game-search query string before it is submitted.
 *
 * PageForms renders its query form as a plain GET form (PFRunQuery.php emits
 * `<form id="pfForm" ... method="get">`), so every one of the 42 fields in
 * `טופס:חיפוש משחק כדורגל` is serialized whether or not the reader filled it.
 * Worse, the results page re-emits each parameter it received as a hidden
 * input, so the empties accumulate across successive searches. A real search
 * setting four filters ships a URL of over 2,000 characters.
 *
 * GA4 stores only the first 1,000 characters of page_location, cutting the URL
 * mid-parameter. Everything past roughly the halfway mark of the form -- the
 * score, points, sets and player filters -- is therefore invisible in
 * analytics, so we cannot tell what readers actually search for.
 *
 * Disabled controls are not serialized, so disabling the empty ones at submit
 * time removes them from the URL: the football form drops from 2,137 characters
 * to 892, and the same search returns an identical result set.
 *
 * The query is unaffected for ANY query form, not just this one: PageForms
 * discards blank parameters in `PFWikiPage::createTemplateCall()` before the
 * template is parsed, so an absent parameter and an empty one produce the same
 * template call. (Do not rely instead on templates defaulting via
 * `{{{Field|}}}` -- some query templates on this wiki use a bare `{{{Field}}}`.)
 *
 * Checkboxes and radios are deliberately excluded: browsers already omit the
 * unticked ones, so there is no bloat to win, and a ticked box is expressed by
 * its `[value]` parameter being sent at all -- `PF_CheckboxInput.php` renders
 * the widget with no value attribute, so the value itself is empty. Stripping
 * empties there would delete the only trace that the box was ticked.
 */
/* The previous query, re-emitted whole as a single hidden input.
 *
 * On a results page PFRunQuery.php replays every parameter it received as a
 * hidden input, and the per-template array collapses via wfArrayToCgi() into one
 * scalar like `QueryGamesTemplate="Season=2013%2F14&EndDate="`. It is non-empty,
 * so the empty-field rule never touches it, and the browser re-encodes it -- so
 * a second search carries a doubly-escaped copy of the first, which is precisely
 * how these URLs reached the length that started all this.
 *
 * Dropping it is safe: the same form also posts the real
 * `QueryGamesTemplate[Field]` controls, and PHP's array subscripts overwrite the
 * scalar, so the blob never reaches the query either way. Identified
 * structurally -- a bracketless name that other controls extend with `[` -- so
 * no template name is hardcoded here.
 */
function gameSearchStaleBlobs(controls) {
    const bracketed = new Set()
    controls.forEach(function (element) {
        const index = element.name ? element.name.indexOf('[') : -1
        if (index > 0) {
            bracketed.add(element.name.slice(0, index))
        }
    })

    const stale = new Set()
    controls.forEach(function (element) {
        if (element.name && element.name.indexOf('[') === -1 && bracketed.has(element.name)) {
            stale.add(element)
        }
    })
    return stale
}


function initGameSearchUrlStrip() {
    // Scoped to the RunQuery form only. Special:FormEdit emits a form with the
    // same `pfForm` id but method="post"; stripping empties there would make it
    // impossible to CLEAR a field, silently keeping the old value on save.
    const queryForms = document.querySelectorAll('form.createbox[method="get"]')

    queryForms.forEach(function (form) {
        if (!form.querySelector('input[name="pfRunQueryFormName"]')) {
            return
        }

        // A native listener, deliberately NOT jQuery. PageForms' own
        // ext.pageforms.submit binds preventDoubleSubmission() on this form, and
        // outside Special:FormEdit that handler dereferences an unassigned
        // variable and throws. jQuery routes every handler it owns through one
        // native listener with no try/catch, so that exception kills the whole
        // jQuery queue -- verified in a browser: bound through jQuery this was a
        // complete no-op and the form still serialized 2,137 characters. A
        // separate native listener is unaffected; the capture phase is belt and
        // braces, not the thing that saves us.
        form.addEventListener('submit', function () {
            const controls = Array.from(form.querySelectorAll('input, select, textarea'))

            // How many controls share each name. The form renders some fields
            // twice (QueryGamesTemplate[PlayerActionMinute], and HomeAway on the
            // volleyball form), and PHP keeps the LAST occurrence of a repeated
            // name. Disabling an empty duplicate would promote the other one and
            // change the reader's results, so repeated names are left alone.
            const nameCounts = new Map()
            controls.forEach(function (element) {
                if (element.name) {
                    nameCounts.set(element.name, (nameCounts.get(element.name) || 0) + 1)
                }
            })

            const staleBlobs = gameSearchStaleBlobs(controls)

            const emptyFields = controls.filter(function (element) {
                if (element.name && nameCounts.get(element.name) > 1) {
                    return false
                }
                if (staleBlobs.has(element)) {
                    return true
                }
                // Checkboxes and radios are excluded: browsers already omit the
                // unticked ones, and PageForms pairs a checkbox with an
                // [is_checkbox] marker whose meaning depends on the [value]
                // parameter being sent at all.
                if (element.type === 'checkbox' || element.type === 'radio') {
                    return false
                }
                // Never touch a control PageForms itself rendered disabled --
                // re-enabling it below would permanently undo that.
                if (element.disabled) {
                    return false
                }
                return typeof element.value === 'string' && element.value.trim() === ''
            })

            emptyFields.forEach(function (element) {
                element.disabled = true
            })

            // Form serialization is synchronous, so re-enabling on the next tick
            // leaves the form usable if the reader navigates back to it.
            setTimeout(function () {
                emptyFields.forEach(function (element) {
                    element.disabled = false
                })
            }, 0)
        }, true)
    })
}
