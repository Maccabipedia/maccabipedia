function initMaccabipediaSpecificPageScripts($, $pageContainer) {
    const specifiedPageScriptMap = {
        'songs-list-page-container': [initSongListPageScripts],
        'common-shirts-list-page-container': [initShirtsListPageScripts]
    }

    if ($pageContainer.length) {
        const pageContainerClasses = Array.from($pageContainer.get(0).classList)

        for (let pageContainerClass of pageContainerClasses) {
            if (specifiedPageScriptMap.hasOwnProperty(pageContainerClass)) {
                specifiedPageScriptMap[pageContainerClass].forEach(fn => fn($, $pageContainer))
                break
            }
        }
    }
}

function initMaccabipediaSpecificClassScripts($, $pageContainer) {
    const specifiedClassScriptMap = {
        'atom-toc': [initTableOfContent],
        'simple-styled-paragraph': [initExpandCollapseParagraph],
        'entity-profile': [initExpandCollapseParagraph],
        'atom-long-text-teaser': [initLongTextTeaser],
        'mp-image-slider-container': [initImagesSlider],
        'mp-promotions-slider-container': [initPromotionsSlider]
    }

    $('.mw-parser-output *[class]').each(function () {
        const $element = $(this)
        const classList = $element.attr('class').split(/\s+/)

        classList.forEach(function (cls) {
            if (Array.isArray(specifiedClassScriptMap[cls])) {
                specifiedClassScriptMap[cls].forEach(fn => fn($, $element, $pageContainer))
            }
        })
    })
}


function initMaccabipediaCommonScripts($, $pageContainer) {
    initAppHeaderListener($)
}


function initMaccabipediaResizeWindowUpdateScripts($, $pageContainer) {
    $(window).on('resize', function () {
        updateSongItemWidth($, $pageContainer)
    })
}


(function ($) {
    $(document).ready(function () {
        const $pageContainer = $('.mw-parser-output > *')

        initMaccabipediaCommonScripts($, $pageContainer)
        initMaccabipediaSpecificClassScripts($, $pageContainer)
        initMaccabipediaSpecificPageScripts($, $pageContainer)
        initMaccabipediaResizeWindowUpdateScripts($, $pageContainer)
    })
}(jQuery))