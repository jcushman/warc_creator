// includes
var system = require('system'),
    http = require('http'),
    webpage = require('webpage');

// args
var address = system.args[1],
    storagePath = system.args[2],
    callbackUrl = system.args[3],
    extraInfo = system.args[4];

extraInfo = extraInfo ? JSON.parse(extraInfo) : {};

// set up PhantomJS request
var page = require('webpage').create();
page.viewportSize = { width: 1024, height: 800 };
if(extraInfo.userAgent)
    page.settings.userAgent = userAgent;

// load page
page.open(address, function (status) {
    if (status !== 'success')
        console.log('Unable to load the address!');
    phantom.exit();
});