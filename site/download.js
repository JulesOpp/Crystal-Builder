// Fills the download buttons from the latest published release.  The
// HTML already points every button at releases/latest, so a blocked API
// call, a rate limit or no JavaScript still leaves a working download;
// this only makes the buttons go straight to the file.
(function () {
  "use strict";

  var API = "https://api.github.com/repos/JulesOpp/Crystal-Builder/releases/latest";

  function detectPlatform() {
    var data = navigator.userAgentData;
    var p = ((data && data.platform) || navigator.platform || "").toLowerCase();
    var ua = navigator.userAgent.toLowerCase();
    if (p.indexOf("mac") >= 0 || ua.indexOf("mac os") >= 0) {
      // iPadOS Safari calls itself a Mac; a Mac has no touch screen.
      return navigator.maxTouchPoints > 1 ? null : "mac";
    }
    if (p.indexOf("win") >= 0 || ua.indexOf("windows") >= 0) return "windows";
    if (p.indexOf("linux") >= 0 || ua.indexOf("linux") >= 0) {
      return ua.indexOf("android") >= 0 ? null : "linux";
    }
    return null;
  }

  // Browsers say "Mac" on Intel and Apple silicon alike, so a Mac is
  // highlighted only when Chromium answers which it is; elsewhere both
  // builds are left as offered, since an Intel Mac handed the arm64
  // DMG as its own gets a file that will not open.
  function macArchitecture() {
    var data = navigator.userAgentData;
    if (!data || !data.getHighEntropyValues) return Promise.resolve(null);
    return data.getHighEntropyValues(["architecture"])
      .then(function (v) { return v.architecture || null; })
      .catch(function () { return null; });
  }

  // On an Intel Mac the main button becomes the x86_64 build, and the
  // smaller link under it the Apple silicon one.
  function preferIntel() {
    var box = document.querySelector('.dl[data-platform="mac"]');
    if (!box) return;
    var main = box.querySelector(".btn");
    var alt = box.querySelector(".dl-alt");
    main.setAttribute("data-asset", "x86_64.dmg");
    alt.setAttribute("data-asset", "arm64.dmg");
    box.querySelector(".dl-label").textContent = "Intel Macs";
    alt.textContent = "Apple silicon Mac? Download the arm64 build";
  }

  function highlight(mine) {
    if (!mine) return;
    var el = document.querySelector('.dl[data-platform="' + mine + '"]');
    if (el && !el.classList.contains("unavailable")) el.classList.add("primary");
  }

  function size(bytes) {
    return Math.round(bytes / 1048576) + " MB";
  }

  function date(iso) {
    return new Date(iso).toLocaleDateString("en-US", {
      year: "numeric", month: "short", day: "numeric"
    });
  }

  function fill(release) {
    var version = release.tag_name;
    var when = date(release.published_at);
    document.querySelectorAll("[data-asset]").forEach(function (link) {
      var suffix = link.getAttribute("data-asset");
      var asset = (release.assets || []).filter(function (a) {
        return a.name.slice(-suffix.length) === suffix;
      })[0];
      var box = link.closest(".dl");
      var main = link.classList.contains("btn");
      var meta = box.querySelector(".dl-meta");
      if (!asset) {
        if (main) {
          box.classList.add("unavailable");
          link.removeAttribute("href");
          link.setAttribute("aria-disabled", "true");
          meta.textContent = "Coming in the next release";
        } else {
          link.hidden = true;
        }
        return;
      }
      link.href = asset.browser_download_url;
      if (main) meta.textContent = version + " · " + when + " · " + size(asset.size);
      else link.title = asset.name + " · " + size(asset.size);
    });
    var notes = document.querySelector("[data-release-link]");
    if (notes) notes.href = release.html_url;
  }

  function lightbox() {
    var box = document.getElementById("lightbox");
    if (!box || !box.showModal) return;
    var big = box.querySelector("img");
    document.querySelectorAll("button.zoom").forEach(function (button) {
      button.addEventListener("click", function () {
        var img = button.querySelector("img");
        big.src = img.currentSrc || img.src;
        big.alt = img.alt;
        box.showModal();
      });
    });
    box.addEventListener("click", function (event) {
      if (event.target === box || event.target === big) box.close();
    });
  }

  lightbox();
  var mine = detectPlatform();
  var arch = mine === "mac" ? macArchitecture() : Promise.resolve(null);
  var release = fetch(API, { headers: { Accept: "application/vnd.github+json" } })
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .catch(function () { return null; /* the static links stand */ });
  Promise.all([arch, release]).then(function (got) {
    if (mine === "mac") {
      if (got[0] === "x86") preferIntel();
      else if (got[0] !== "arm") mine = null;
    }
    if (got[1]) fill(got[1]);
    highlight(mine);
  });
})();
