/* IMPORTANT: Load CanvasJS from CDN!
This must loaded before the initIndexPageChartSection
*/
mw.loader.load('https://canvasjs.com/assets/script/jquery.canvasjs.min.js');

function initMaccabipediaCharts(elPageContent) {
    jQuery(document).ready(function ($) {
        function initChars() {
            if (typeof CanvasJS !== "undefined" && typeof CanvasJS.Chart === "function") {
                initMultipleColumnsChart(elPageContent);
                initPieChart(elPageContent);
                initStackedBarChart(elPageContent);

                isInitedChars = true;
            } else {
                setTimeout(initChars, 50);
            }
        }

        initChars();
    });
}
function initMultipleColumnsChart(elPageContent) {
    var multipleColumnsChartContainers = $(elPageContent).find('.maccabipedia-multiple-column-chart-container');
    multipleColumnsChartContainers.each(function (multipleColumnChartIndex, element) {
        var currChartRendererContainer = $(element).find('.chart-renderer');
        var currChartData = $(element).find('.chart-data .chart-data-hidden');
        var chartMetaData = $(element).find('.chart-meta-data');


        var multipleColumnChartOptions = {
            animationEnabled: true,
            axisY: {
                title: typeof $(chartMetaData).data('axis-title') !== 'undefined' ? $(chartMetaData).data('axis-title') : null,
                interval: typeof $(chartMetaData).data('axis-interval') !== 'undefined' ? $(chartMetaData).data('axis-interval') : null,
                maximum: typeof $(chartMetaData).data('axis-maximum') !== 'undefined' ? $(chartMetaData).data('axis-maximum') : null
            },
            toolTip: {
                content: "{label}: {y} {legendText}"
            },
            data: [{
                type: 'column',
                name: (typeof $(chartMetaData).data('option1-name') !== 'undefined' ? $(chartMetaData).data('option1-name') : null),
                showInLegend: true,
                color: (typeof $(chartMetaData).data('option1-color') !== 'undefined' ? $(chartMetaData).data('option1-color') : null),
                dataPoints: currChartData.map(function (index) {
                    return {
                        label: (typeof $(this).data('title') !== 'undefined' ? $(this).data('title') : null),
                        y: (typeof $(this).data('first-axis') !== 'undefined' ? $(this).data('first-axis') : null),
                        optionName: (typeof $(chartMetaData).data('option1-name') !== 'undefined' ? $(chartMetaData).data('option1-name') : null)
                    };
                }).get()
            }, {
                type: 'column',
                name: (typeof $(chartMetaData).data('option2-name') !== 'undefined' ? $(chartMetaData).data('option2-name') : null),
                showInLegend: true,
                color: (typeof $(chartMetaData).data('option2-color') !== 'undefined' ? $(chartMetaData).data('option2-color') : null),
                dataPoints: currChartData.map(function (index) {
                    return {
                        label: (typeof $(this).data('title') !== 'undefined' ? $(this).data('title') : null),
                        y: (typeof $(this).data('second-axis') !== 'undefined' ? $(this).data('second-axis') : null),
                        optionName: (typeof $(chartMetaData).data('option2-name') !== 'undefined' ? $(chartMetaData).data('option2-name') : null)
                    };
                }).get()
            }]
        };

        $(currChartRendererContainer).CanvasJSChart(multipleColumnChartOptions);
    });
}
function initStackedBarChart(elPageContent) {
    var stackedBarChartContainers = $(elPageContent).find('.maccabipedia-stacked-bar-chart-container');

    stackedBarChartContainers.each(function (stackedBarChartIndex, element) {
        var currChartRendererContainer = $(element).find('.chart-renderer');
        var currChartData = $(element).find('.chart-data .chart-data-hidden');
        var chartMetaData = $(element).find('.chart-meta-data');

        var currChartDataSeriesNames = (typeof chartMetaData.data('categories') !== 'undefined' ? chartMetaData.data('categories').split(', ') : []);
        var currChartBarBgcs = (typeof chartMetaData.data('bar-bgcs') !== 'undefined' ? chartMetaData.data('bar-bgcs').split(', ') : []);
        var currChartBarTextColors = (typeof chartMetaData.data('bar-text-color') !== 'undefined' ? chartMetaData.data('bar-text-color').split(', ') : []);

        var currChartCategories = currChartData.map(function (currChartDataIndex) {
            var currChartCategoryValues = (typeof $(this).data('values') !== 'undefined' ? $(this).data('values').split(', ').map(Number) : []);
            var currChartCategoryValuesSum = 0;

            for (var currChartCategoryValuesSumIndex = 0; currChartCategoryValuesSumIndex < currChartCategoryValues.length; currChartCategoryValuesSumIndex++) {
                currChartCategoryValuesSum = currChartCategoryValuesSum + currChartCategoryValues[currChartCategoryValuesSumIndex];
            }

            return {
                label: (typeof $(this).data('name') !== 'undefined' ? $(this).data('name') : null),
                values: currChartCategoryValues,
                valuesSum: currChartCategoryValuesSum
            }
        }).get();

        var currChartCategoriesDataParsed = [];
        for (var currChartCategoriesDataParsedMapIndex = 0; currChartCategoriesDataParsedMapIndex < currChartCategories[0].values.length; currChartCategoriesDataParsedMapIndex++) {

            var currCategoryDataPoints = [];
            for (var currCategoryDataPointsIndex = 0; currCategoryDataPointsIndex < currChartCategories.length; currCategoryDataPointsIndex++) {
                var currCategoryData = currChartCategories[currCategoryDataPointsIndex]
                var currCategoryDataPointsTotal = currCategoryData.valuesSum;
                var currCategoryDataPointsValue = currCategoryData.values[currChartCategoriesDataParsedMapIndex];
                var currCategoryDataPointsPercentage = ((currCategoryDataPointsValue / currCategoryDataPointsTotal) * 100).toFixed(0);

                currCategoryDataPoints.push({
                    label: currCategoryData.label,
                    y: currCategoryDataPointsValue,
                    indexLabel: (currCategoryDataPointsPercentage > 0.0001) ? currCategoryDataPointsPercentage + '%' : '',
                    indexLabelPlacement: "inside",
                    indexLabelFontColor: currChartBarTextColors[currChartCategoriesDataParsedMapIndex],
                    indexLabelFontWeight: "bold",
                    indexLabelFontFamily: "'Assistant',sans-serif",
                    indexLabelFontSize: 12,
                    color: currChartBarBgcs[currChartCategoriesDataParsedMapIndex]
                })
            }

            currChartCategoriesDataParsed.push({
                type: "stackedBar100",
                name: currChartDataSeriesNames[currChartCategoriesDataParsedMapIndex],
                showInLegend: true,
                legendMarkerColor: currChartBarBgcs[currChartCategoriesDataParsedMapIndex],
                dataPoints: currCategoryDataPoints
            });
        }

        var stackedBarChartOptions = {
            animationEnabled: true,
            axisY: {
                suffix: "",
                reversed: true,
                lineThickness: 0,
                gridThickness: 0,
                tickLength: 0,
                labelFormatter: function () {
                    return ""; // Removes the labels
                }
            },
            legend: {
                reversed: true
            },
            toolTip: {
                shared: true
            },
            data: currChartCategoriesDataParsed
        };

        $(currChartRendererContainer).CanvasJSChart(stackedBarChartOptions);
    });
}
function initPieChart(elPageContent) {
    var pieChartContainers = $(elPageContent).find('.maccabipedia-pie-chart-container');
    var pieChartColorPalette = ['#195da6', '#ffdd00', '#a6a6a6', '#1a1a1a', '#021952', '#0b2a4b'];

    pieChartContainers.each(function (pieChartIndex, element) {
        var currChartRendererContainer = $(element).find('.chart-renderer');
        var currChartData = $(element).find('.chart-data .chart-data-hidden');
        var chartMetaData = $(element).find('.chart-meta-data');

        var pieChartOptions = {
            animationEnabled: true,
            legend: {
                horizontalAlign: "right",
                verticalAlign: "center"
            },
            data: [{
                type: "pie",
                showInLegend: true,
                toolTipContent: "<b>{name}</b>: {y} זכיות (#percent%)",
                indexLabel: "{name}",
                legendText: "{name} (#percent%)",
                dataPoints: currChartData.map(function (currChartDataIndex) {
                    return {
                        name: (typeof $(this).data('name') !== 'undefined' ? $(this).data('name') : null),
                        color: pieChartColorPalette[currChartDataIndex],
                        y: (typeof $(this).data('amount') !== 'undefined' ? $(this).data('amount') : null),
                    };
                }).get()
            }]
        };

        $(currChartRendererContainer).CanvasJSChart(pieChartOptions);
    });
}



/* sending mails (fanzine) */
function sendMail() {
    var data = {
        service_id: 'service_vxigmjz',
        template_id: 'template_2nrbvsd',
        user_id: 'V1S5vDtbtB7zZxrSP',
        template_params: {
            'username': 'James',
            'g-recaptcha-response': '03AHJ_ASjnLA214KSNKFJAK12sfKASfehbmfd...'
        }
    };

    $.ajax('https://api.emailjs.com/api/v1.0/email/send', {
        type: 'POST',
        data: JSON.stringify(data),
        contentType: 'application/json'
    }).done(function () {
        alert('Your mail is sent!');
    }).fail(function (error) {
        alert('Oops... ' + JSON.stringify(error));
    });
}



$('#fanzine-conact').submit(function (event) {
    event.preventDefault();
    sendMail();
});




/* כל הסקריפטים שנכתבים כאן ייטענו עבור כל המשתמשים בכל טעינת עמוד. */
/* הצגת ערכים הנטענים באופן דינמי */
mw.loader.using('mediawiki.legacy.wikibits', function () {
    importScript('MediaWiki:LoadingContent.js');
});

function escapeSelector(s) {
    return s.replace(/(:|\.|\[|\])/g, "\\$1");
}

/* --- Jump to ID - Handle links with @href started with '#' only --- */
/* Tabber tabs are excluded: a tab links to its own panel, right below it, so
   the jump scrolled the strip off screen on every click. The tab switches
   itself and keeps the URL in sync. */
$(document).on('click', 'a[href^="#"]:not(.tabber__tab)', function (e) {
    // target element id
    var id = $(escapeSelector($(this).attr('href')));
    // target element
    var $id = $(id);
    if ($id.length === 0) {
        return;
    }
    // prevent standard hash navigation (avoid blinking in IE)
    e.preventDefault();
    // top position relative to the document
    var pos = $id.offset().top - 50;
    // animated top scrolling
    $('body, html').animate({ scrollTop: pos }, 950);
});