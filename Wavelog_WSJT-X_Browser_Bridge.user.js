// ==UserScript==
// @name         Wavelog WSJT-X Bridge
// @namespace    http://tampermonkey.net/
// @version      1.7
// @description  Guarantees data injection first, then breaks sandbox to trigger lookups
// @match        *://*/index.php/qso*
// @match        *://*/qso*
// @grant        unsafeWindow
// ==/UserScript==

(function() {
    'use strict';

    const wsUrl = "ws://127.0.0.1:2334";
    let socket;

    // Grab the page's actual window object (bypassing the Tampermonkey sandbox)
    const pageWindow = (typeof unsafeWindow !== 'undefined') ? unsafeWindow : window;

    function triggerWavelogLookup(callsign, locator) {
        // 1. ALWAYS grab elements natively first to guarantee data gets in the boxes
        const callsignInput = document.getElementById("callsign") || document.querySelector("input[name='callsign']");
        const locatorInput = document.getElementById("locator") || document.querySelector("input[name='locator']");

        if (!callsignInput) {
            console.warn("⚠️ Could not find #callsign input on the page.");
            return;
        }

        console.log(`🚀 [Bridge] Injecting: ${callsign} (Grid: ${locator})`);

        // 2. Write the value directly to the HTML DOM (this will NEVER fail to show up)
        callsignInput.value = callsign;
        
        // Dispatch basic browser events
        callsignInput.dispatchEvent(new Event('input', { bubbles: true }));
        callsignInput.dispatchEvent(new Event('change', { bubbles: true }));

        // 3. Break out of sandbox to access Wavelog's jQuery
        const $ = pageWindow.$ || pageWindow.jQuery;
        if ($) {
            const $callsign = $(callsignInput);
            // Clear jQuery's internal change tracker cache
            $callsign.data('oldVal', ''); 
            $callsign.trigger('input');
            $callsign.trigger('change');
            $callsign.trigger('keyup');

            // Force Wavelog to execute its blur listener
            setTimeout(() => {
                $callsign.trigger('blur');
                console.log("🎯 [Bridge] Triggered jQuery blur on callsign.");
            }, 100);
        } else {
            // Native fallback if jQuery is inaccessible
            setTimeout(() => {
                callsignInput.blur();
                console.log("🎯 [Bridge] Triggered native blur fallback.");
            }, 100);
        }

        // 4. Try running Wavelog's native functions directly
        try {
            if (typeof pageWindow.lookupCheck === "function") {
                pageWindow.lookupCheck();
                console.log("🎯 [Bridge] Invoked lookupCheck() directly.");
            } else if (typeof pageWindow.callsign_lookup === "function") {
                pageWindow.callsign_lookup();
                console.log("🎯 [Bridge] Invoked callsign_lookup() directly.");
            }
        } catch (err) {
            console.error("⚠️ Failed executing Wavelog lookup function:", err);
        }

        // 5. Inject locator safely with a delay so Wavelog's API response doesn't erase it
        if (locator && locatorInput) {
            setTimeout(() => {
                locatorInput.value = locator;
                locatorInput.dispatchEvent(new Event('input', { bubbles: true }));
                locatorInput.dispatchEvent(new Event('change', { bubbles: true }));

                if ($) {
                    const $locator = $(locatorInput);
                    $locator.trigger('input');
                    $locator.trigger('change');
                    $locator.trigger('blur');
                } else {
                    locatorInput.blur();
                }
                console.log(`🛰️ [Bridge] Injected locator grid: ${locator}`);
            }, 800); // 800ms gives Wavelog's database lookup plenty of time to resolve
        }
    }

    function connect() {
        console.log("🔌 Connecting to WSJT-X Python Bridge...");
        socket = new WebSocket(wsUrl);

        socket.onopen = () => {
            console.log("✅ Connected to WSJT-X Python Bridge!");
        };

        socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                console.log("📥 Received from Bridge:", data);

                if (data.callsign) {
                    triggerWavelogLookup(data.callsign, data.locator);
                }
            } catch (err) {
                console.error("❌ Failed to process socket message:", err);
            }
        };

        socket.onclose = () => {
            console.log("❌ Connection lost. Reconnecting in 5 seconds...");
            setTimeout(connect, 5000);
        };

        socket.onerror = (err) => {
            console.error("WebSocket Error:", err);
        };
    }

    // Start connection
    connect();
})();