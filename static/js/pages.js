const Pages = (() => {
  const { escapeHtml, firstName, toast, fmtDate, openModal, tally, starsReadonly, starPicker, wireStarPicker, debounce, volumeUnitLabel, ozToDisplay, displayToOz } = UI;

  // Beer styles are fetched once per page load and cached - they rarely
  // change mid-session, and this list can be fairly long.
  let _stylesCache = null;
  async function getBeerStyles() {
    if (_stylesCache) return _stylesCache;
    try {
      const res = await Api.beerStyles();
      _stylesCache = res.styles || [];
    } catch (e) {
      _stylesCache = [];
    }
    return _stylesCache;
  }

  // Common bottle/can sizes shown in the size field's suggestions,
  // defined natively for each unit system rather than converting one into
  // the other - metric sizes in mL are round European bottle/can
  // standards, imperial sizes in oz are genuine US customary sizes (a
  // standard 12 oz bottle, 16 oz pint can, 19.2 oz "stovepipe" single,
  // 22 oz bomber, 32 oz crowler, 64 oz growler), not a converted 11.2 oz
  // or 25.4 oz that nobody actually buys.
  const COMMON_SIZES_ML = [250, 330, 375, 440, 500, 750, 1500];
  const COMMON_SIZES_OZ = [8, 12, 16, 19.2, 22, 32, 64];

  async function getSizeSuggestions(account) {
    let rememberedOz = [];
    try {
      rememberedOz = await Api.usedSizes(); // this user's own past entries, most-used first
    } catch (e) {
      rememberedOz = [];
    }
    const commonOz =
      account.unit_system === "metric" ? COMMON_SIZES_ML.map((ml) => displayToOz(ml, "metric")) : COMMON_SIZES_OZ;
    // Merge remembered sizes with the fixed common list, then sort
    // numerically for a sensible dropdown order. Dedup on the rounded
    // value actually displayed - a remembered size landing on the same
    // shown number as a common one (e.g. 330 mL either way) should only
    // appear once; remembered values are deduped first so an exact past
    // entry (not just something close to a common size) wins that slot.
    const seen = new Set();
    const displayValues = [];
    for (const oz of [...rememberedOz, ...commonOz]) {
      const displayVal = ozToDisplay(oz, account.unit_system);
      if (displayVal === "" || seen.has(displayVal)) continue;
      seen.add(displayVal);
      displayValues.push(displayVal);
    }
    displayValues.sort((a, b) => a - b);
    return displayValues;
  }

  // ---------- Beer/brewery autocomplete used inside the add/edit entry modal ----------

  function wireBeerAutocomplete(root, { onPick }) {
    const input = root.querySelector('[name="beer_search"]');
    const list = root.querySelector(".suggest-list[data-for=beer]");
    const hiddenId = root.querySelector('input[name="beer_id"]');
    const breweryInput = root.querySelector('[name="new_brewery_name"]');
    const breweryHiddenId = root.querySelector('input[name="brewery_id"]');
    const styleInput = root.querySelector('[name="style"]');
    const abvInput = root.querySelector('[name="abv"]');
    const pickedNote = root.querySelector(".picked-note");

    const search = debounce(async (q) => {
      if (q.length === 1) {
        list.innerHTML = "";
        list.style.display = "none";
        return;
      }
      try {
        const results = await Api.searchBeers(q);
        if (!results.length) {
          list.innerHTML = `<div class="suggest-item">No matches &mdash; a new beer will be created</div>`;
        } else {
          list.innerHTML = results
            .map(
              (b) =>
                `<div class="suggest-item" data-id="${b.id}" data-name="${escapeHtml(b.name)}" data-brewery="${escapeHtml(
                  b.brewery.name
                )}" data-style="${escapeHtml(b.style || "")}" data-abv="${b.abv ?? ""}">
                  ${escapeHtml(b.name)}<div class="b">${escapeHtml(b.brewery.name)}${b.style ? " &middot; " + escapeHtml(b.style) : ""}</div>
                </div>`
            )
            .join("");
        }
        list.style.display = "block";
      } catch (e) {
        list.style.display = "none";
      }
    }, 220);

    input.addEventListener("input", () => {
      hiddenId.value = "";
      pickedNote.textContent = "";
      search(input.value.trim());
    });
    input.addEventListener("focus", () => {
      if (list.innerHTML) {
        list.style.display = "block";
      } else {
        search(input.value.trim());
      }
    });
    document.addEventListener("click", (e) => {
      if (!list.contains(e.target) && e.target !== input) list.style.display = "none";
    });

    list.addEventListener("click", (e) => {
      const item = e.target.closest(".suggest-item[data-id]");
      if (!item) return;
      hiddenId.value = item.dataset.id;
      input.value = item.dataset.name;
      breweryInput.value = item.dataset.brewery;
      breweryInput.disabled = true;
      if (breweryHiddenId) breweryHiddenId.value = "";
      styleInput.value = item.dataset.style || "";
      abvInput.value = item.dataset.abv || "";
      pickedNote.textContent = `Using the existing entry for ${item.dataset.name} (${item.dataset.brewery}).`;
      list.style.display = "none";
      if (onPick) onPick(item.dataset.id);
    });

    // Typing again after a pick should free up the brewery field
    input.addEventListener("input", () => {
      if (!hiddenId.value) breweryInput.disabled = false;
    });
  }

  function isoDateInputHtml(name, value) {
    return `<div class="date-field">
      <input class="input" type="text" inputmode="numeric" autocomplete="off" placeholder="YYYY-MM-DD" maxlength="10" name="${name}" value="${escapeHtml(value || "")}" data-iso-date />
      <button type="button" class="date-picker-btn" aria-label="Pick a date">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="4" width="18" height="18" rx="2"></rect>
          <line x1="16" y1="2" x2="16" y2="6"></line>
          <line x1="8" y1="2" x2="8" y2="6"></line>
          <line x1="3" y1="10" x2="21" y2="10"></line>
        </svg>
      </button>
    </div>`;
  }

  function wireIsoDateInputs(root) {
    root.querySelectorAll("[data-iso-date]").forEach((input) => {
      input.addEventListener("input", () => {
        const digits = input.value.replace(/\D/g, "").slice(0, 8);
        let out = digits;
        if (digits.length > 4) out = digits.slice(0, 4) + "-" + digits.slice(4);
        if (digits.length > 6) out = digits.slice(0, 4) + "-" + digits.slice(4, 6) + "-" + digits.slice(6);
        input.value = out;
      });
      wireDatePickerPopup(input);
    });
  }

  // Only one calendar popup should be open at a time across the whole form.
  let _closeActiveDatePopup = null;

  function wireDatePickerPopup(input) {
    const wrap = input.closest(".date-field");
    const btn = wrap && wrap.querySelector(".date-picker-btn");
    if (!wrap || !btn) return;

    let popupEl = null;
    let viewYear, viewMonth; // viewMonth is 0-indexed

    function parseInputDate() {
      const m = input.value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
      return m ? { y: Number(m[1]), m: Number(m[2]) - 1, d: Number(m[3]) } : null;
    }

    function setValue(y, m, d) {
      const pad = (n) => String(n).padStart(2, "0");
      input.value = `${y}-${pad(m + 1)}-${pad(d)}`;
      input.dispatchEvent(new Event("input", { bubbles: true }));
    }

    function onDocClick(e) {
      if (popupEl && !popupEl.contains(e.target) && e.target !== btn) closePopup();
    }
    function onKeydown(e) {
      if (e.key === "Escape") {
        e.stopPropagation();
        closePopup();
      }
    }

    function closePopup() {
      if (!popupEl) return;
      popupEl.remove();
      popupEl = null;
      document.removeEventListener("click", onDocClick);
      document.removeEventListener("keydown", onKeydown, true);
      if (_closeActiveDatePopup === closePopup) _closeActiveDatePopup = null;
    }

    function renderCalendar() {
      const selected = parseInputDate();
      const firstOfMonth = new Date(viewYear, viewMonth, 1);
      const startWeekday = firstOfMonth.getDay();
      const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
      const today = new Date();
      const monthLabel = firstOfMonth.toLocaleDateString(undefined, { month: "long", year: "numeric" });

      let cells = "";
      for (let i = 0; i < startWeekday; i++) cells += `<span class="cal-day empty"></span>`;
      for (let d = 1; d <= daysInMonth; d++) {
        const isSelected = !!selected && selected.y === viewYear && selected.m === viewMonth && selected.d === d;
        const isToday = today.getFullYear() === viewYear && today.getMonth() === viewMonth && today.getDate() === d;
        cells += `<button type="button" class="cal-day${isSelected ? " selected" : ""}${isToday ? " today" : ""}" data-day="${d}">${d}</button>`;
      }

      popupEl.innerHTML = `
        <div class="cal-header">
          <button type="button" class="cal-nav" data-nav="-1" aria-label="Previous month">&lsaquo;</button>
          <span class="cal-month-label">${escapeHtml(monthLabel)}</span>
          <button type="button" class="cal-nav" data-nav="1" aria-label="Next month">&rsaquo;</button>
        </div>
        <div class="cal-weekdays"><span>S</span><span>M</span><span>T</span><span>W</span><span>T</span><span>F</span><span>S</span></div>
        <div class="cal-grid">${cells}</div>
        <div class="cal-footer">
          <button type="button" class="cal-today-btn">Today</button>
          <button type="button" class="cal-clear-btn">Clear</button>
        </div>
      `;
    }

    function openPopup() {
      if (popupEl) return;
      if (_closeActiveDatePopup) _closeActiveDatePopup();
      _closeActiveDatePopup = closePopup;

      const selected = parseInputDate();
      const now = new Date();
      viewYear = selected ? selected.y : now.getFullYear();
      viewMonth = selected ? selected.m : now.getMonth();

      popupEl = document.createElement("div");
      popupEl.className = "date-popup";
      wrap.appendChild(popupEl);
      renderCalendar();

      popupEl.addEventListener("click", (e) => {
        e.stopPropagation();
        const dayBtn = e.target.closest(".cal-day[data-day]");
        if (dayBtn) {
          setValue(viewYear, viewMonth, Number(dayBtn.dataset.day));
          closePopup();
          return;
        }
        const navBtn = e.target.closest(".cal-nav");
        if (navBtn) {
          viewMonth += Number(navBtn.dataset.nav);
          if (viewMonth < 0) {
            viewMonth = 11;
            viewYear--;
          } else if (viewMonth > 11) {
            viewMonth = 0;
            viewYear++;
          }
          renderCalendar();
          return;
        }
        if (e.target.closest(".cal-today-btn")) {
          const t = new Date();
          setValue(t.getFullYear(), t.getMonth(), t.getDate());
          closePopup();
          return;
        }
        if (e.target.closest(".cal-clear-btn")) {
          input.value = "";
          input.dispatchEvent(new Event("input", { bubbles: true }));
          closePopup();
        }
      });

      document.addEventListener("click", onDocClick);
      document.addEventListener("keydown", onKeydown, true); // capture: must intercept Escape before the modal's own (bubble-phase) Escape-to-close handler sees it
    }

    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (popupEl) closePopup();
      else openPopup();
    });
  }

  function todayIsoLocal() {
    // Local calendar date, not UTC - see the note in isValidIsoDateOrEmpty
    // for why a toISOString()-based approach silently gives the wrong day
    // for part of the evening/night in any timezone ahead of UTC.
    const d = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }

  function isValidIsoDateOrEmpty(value) {
    if (!value) return true;
    const m = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!m) return false;
    const year = Number(m[1]);
    const month = Number(m[2]);
    const day = Number(m[3]);
    // Constructed and checked entirely in local time - no UTC round-trip.
    // (An earlier version used `new Date(value + "T00:00:00")` then compared
    // against `.toISOString()`, which converts to UTC: for anyone in a
    // timezone ahead of UTC, local midnight rolls back to the previous
    // calendar day in UTC, so a perfectly valid date like "2026-08-26"
    // would come back as "2026-08-25" and fail the comparison. Comparing
    // local year/month/day components directly sidesteps that entirely,
    // while still correctly catching bogus dates like "2026-02-30".)
    const d = new Date(year, month - 1, day);
    return d.getFullYear() === year && d.getMonth() === month - 1 && d.getDate() === day;
  }

  function wireBreweryAutocomplete(root) {
    const input = root.querySelector('[name="new_brewery_name"]');
    const list = root.querySelector(".suggest-list[data-for=brewery]");
    const hiddenId = root.querySelector('input[name="brewery_id"]');
    if (!input || !list || !hiddenId) return;

    const search = debounce(async (q) => {
      if (input.disabled || q.length === 1) {
        list.innerHTML = "";
        list.style.display = "none";
        return;
      }
      try {
        const results = await Api.searchBreweries(q);
        if (!results.length) {
          list.style.display = "none";
          return;
        }
        list.innerHTML = results
          .map((b) => `<div class="suggest-item" data-id="${b.id}" data-name="${escapeHtml(b.name)}">${escapeHtml(b.name)}</div>`)
          .join("");
        list.style.display = "block";
      } catch (e) {
        list.style.display = "none";
      }
    }, 220);

    input.addEventListener("input", () => {
      hiddenId.value = "";
      search(input.value.trim());
    });
    input.addEventListener("focus", () => {
      if (input.disabled) return;
      if (list.innerHTML) {
        list.style.display = "block";
      } else {
        search(input.value.trim());
      }
    });
    document.addEventListener("click", (e) => {
      if (!list.contains(e.target) && e.target !== input) list.style.display = "none";
    });
    list.addEventListener("click", (e) => {
      const item = e.target.closest(".suggest-item[data-id]");
      if (!item) return;
      hiddenId.value = item.dataset.id;
      input.value = item.dataset.name;
      list.style.display = "none";
    });
  }

  function wireStyleAutocomplete(root, styles) {
    const input = root.querySelector('[name="style"]');
    const list = root.querySelector(".suggest-list[data-for=style]");
    if (!input || !list || !styles || !styles.length) return;

    function render(q) {
      const query = q.trim().toLowerCase();
      const matches = (query ? styles.filter((s) => s.toLowerCase().includes(query)) : styles).slice(0, 8);
      if (!matches.length) {
        list.style.display = "none";
        return;
      }
      list.innerHTML = matches.map((s) => `<div class="suggest-item" data-value="${escapeHtml(s)}">${escapeHtml(s)}</div>`).join("");
      list.style.display = "block";
    }

    input.addEventListener("input", () => render(input.value));
    input.addEventListener("focus", () => {
      if (!input.disabled) render(input.value);
    });
    document.addEventListener("click", (e) => {
      if (!list.contains(e.target) && e.target !== input) list.style.display = "none";
    });
    list.addEventListener("click", (e) => {
      const item = e.target.closest(".suggest-item[data-value]");
      if (!item) return;
      input.value = item.dataset.value;
      list.style.display = "none";
    });
  }

  function entryFormHtml(entry, account, styles, sizeSuggestions) {
    const sizeListId = `size-suggestions-${entry ? entry.id : "new"}-${Math.random().toString(36).slice(2, 8)}`;
    const tradingRow = account.trading_enabled
      ? `<div class="field">
           <label>Trading status</label>
           <select class="input" name="trade_status">
             <option value="none" ${entry?.trade_status === "none" || !entry ? "selected" : ""}>Not trading</option>
             <option value="ft" ${entry?.trade_status === "ft" ? "selected" : ""}>For Trade (FT)</option>
             <option value="iso" ${entry?.trade_status === "iso" ? "selected" : ""}>In Search Of (ISO)</option>
           </select>
         </div>`
      : "";
    const locationRow = account.show_fridge_column
      ? `<div class="field">
           <label>Location</label>
           <select class="input" name="location">
             <option value="cellar" ${!entry || entry.location === "cellar" ? "selected" : ""}>In Cellar</option>
             <option value="fridge" ${entry?.location === "fridge" ? "selected" : ""}>In Fridge</option>
           </select>
         </div>`
      : `<input type="hidden" name="location" value="cellar" />`;
    const customLocationRow = account.show_location_column
      ? `<div class="field">
           <label>Shelf / custom location <span class="subtle">(optional)</span></label>
           <input class="input" name="custom_location" value="${escapeHtml(entry?.custom_location || "")}" placeholder="e.g. Rack 3, back left" />
         </div>`
      : "";

    return `
      <button class="modal-close" data-close>&times;</button>
      <h2>${entry ? "Edit bottle" : "Add a bottle"}</h2>
      <form data-entry-form>
        <div class="field suggest-wrap">
          <label>Beer</label>
          <input class="input" name="beer_search" autocomplete="off" placeholder="Start typing a beer name&hellip;"
                 value="${entry ? escapeHtml(entry.beer.name) : ""}" ${entry ? "disabled" : ""} />
          <input type="hidden" name="beer_id" value="${entry ? entry.beer.id : ""}" />
          <div class="suggest-list" data-for="beer" style="display:none"></div>
          <div class="field-hint picked-note"></div>
        </div>
        <div class="field-row">
          <div class="field suggest-wrap">
            <label>Brewery</label>
            <input class="input" name="new_brewery_name" autocomplete="off" placeholder="Start typing a brewery name&hellip;"
                   value="${entry ? escapeHtml(entry.beer.brewery.name) : ""}" ${entry ? "disabled" : ""} />
            <input type="hidden" name="brewery_id" value="" />
            <div class="suggest-list" data-for="brewery" style="display:none"></div>
          </div>
          <div class="field suggest-wrap">
            <label>Style <span class="subtle">(optional)</span></label>
            <input class="input" name="style" autocomplete="off" placeholder="Start typing a style&hellip;"
                   value="${entry ? escapeHtml(entry.beer.style || "") : ""}" ${entry ? "disabled" : ""} />
            <div class="suggest-list" data-for="style" style="display:none"></div>
          </div>
        </div>
        <div class="field-row">
          <div class="field">
            <label>ABV % <span class="subtle">(optional)</span></label>
            <input class="input" type="number" step="0.1" min="0" max="100" name="abv"
                   value="${entry?.beer.abv ?? ""}" ${entry ? "disabled" : ""} />
          </div>
          <div class="field">
            <label>Bottle size, ${volumeUnitLabel(account.unit_system)} <span class="subtle">(optional)</span></label>
            <input class="input" type="number" step="${account.unit_system === "metric" ? "1" : "0.1"}" min="0" name="size_display" value="${ozToDisplay(entry?.size_oz, account.unit_system)}" list="${sizeListId}" autocomplete="off" />
            <datalist id="${sizeListId}">
              ${(sizeSuggestions || []).map((v) => `<option value="${v}"></option>`).join("")}
            </datalist>
          </div>
        </div>
        <div class="field-row">
          <div class="field">
            <label>Quantity</label>
            <input class="input" type="number" min="0" step="1" name="quantity" value="${entry ? entry.quantity : 1}" required />
          </div>
          ${locationRow}
        </div>
        ${customLocationRow}
        <div class="field-row">
          <div class="field">
            <label>Bottle date <span class="subtle">(optional)</span></label>
            ${isoDateInputHtml("bottle_date", entry?.bottle_date)}
          </div>
          <div class="field">
            <label>Best before / drink by <span class="subtle">(optional)</span></label>
            ${isoDateInputHtml("best_before", entry?.best_before)}
          </div>
        </div>
        ${tradingRow}
        <div class="field">
          <label>Batch notes <span class="subtle">(optional)</span></label>
          <textarea class="input" name="batch_notes" placeholder="Batch #, where you got it, aging plan&hellip;">${escapeHtml(
            entry?.batch_notes || ""
          )}</textarea>
        </div>
        <div class="form-error" data-error style="display:none"></div>
        <div class="form-actions">
          <button type="submit" class="btn btn-primary btn-block">${entry ? "Save changes" : "Add to cellar"}</button>
        </div>
      </form>
    `;
  }

  async function openEntryModal(entry, account, onSaved) {
    const styles = await getBeerStyles();
    const sizeSuggestions = await getSizeSuggestions(account);
    openModal(entryFormHtml(entry, account, styles, sizeSuggestions), {
      onMount(modalEl, close) {
        modalEl.querySelector("[data-close]").addEventListener("click", close);
        wireIsoDateInputs(modalEl);
        if (!entry) {
          wireBeerAutocomplete(modalEl, {});
          wireBreweryAutocomplete(modalEl);
          wireStyleAutocomplete(modalEl, styles);
        }
        const form = modalEl.querySelector("[data-entry-form]");
        const errorBox = modalEl.querySelector("[data-error]");
        form.addEventListener("submit", async (e) => {
          e.preventDefault();
          errorBox.style.display = "none";
          const fd = new FormData(form);
          const submitBtn = form.querySelector('button[type="submit"]');
          submitBtn.disabled = true;
          try {
            const bottleDate = fd.get("bottle_date")?.trim() || "";
            const bestBefore = fd.get("best_before")?.trim() || "";
            if (!isValidIsoDateOrEmpty(bottleDate)) throw new Error(`"${bottleDate}" isn't a valid date - use YYYY-MM-DD.`);
            if (!isValidIsoDateOrEmpty(bestBefore)) throw new Error(`"${bestBefore}" isn't a valid date - use YYYY-MM-DD.`);
            if (entry) {
              const payload = {
                quantity: Number(fd.get("quantity")),
                size_oz: displayToOz(fd.get("size_display"), account.unit_system),
                location: fd.get("location") || "cellar",
                custom_location: fd.get("custom_location") || null,
                bottle_date: bottleDate || null,
                best_before: bestBefore || null,
                batch_notes: fd.get("batch_notes") || null,
              };
              if (account.trading_enabled) payload.trade_status = fd.get("trade_status") || "none";
              await Api.patchEntry(entry.id, payload);
            } else {
              const beerId = fd.get("beer_id");
              const payload = {
                location: fd.get("location") || "cellar",
                custom_location: fd.get("custom_location") || null,
                quantity: Number(fd.get("quantity")),
                size_oz: displayToOz(fd.get("size_display"), account.unit_system),
                bottle_date: bottleDate || null,
                best_before: bestBefore || null,
                batch_notes: fd.get("batch_notes") || null,
                trade_status: account.trading_enabled ? fd.get("trade_status") || "none" : "none",
              };
              if (beerId) {
                payload.beer_id = Number(beerId);
              } else {
                const name = fd.get("beer_search")?.trim();
                if (!name) throw new Error("Enter a beer name.");
                const pickedBreweryId = fd.get("brewery_id");
                payload.beer = {
                  name,
                  brewery_id: pickedBreweryId ? Number(pickedBreweryId) : null,
                  new_brewery_name: pickedBreweryId ? null : fd.get("new_brewery_name")?.trim() || null,
                  style: fd.get("style")?.trim() || null,
                  abv: fd.get("abv") ? Number(fd.get("abv")) : null,
                };
                if (!payload.beer.brewery_id && !payload.beer.new_brewery_name) throw new Error("Enter a brewery name.");
              }
              await Api.addEntry(payload);
            }
            close();
            toast(entry ? "Bottle updated." : "Added to your cellar.");
            onSaved();
          } catch (err) {
            errorBox.textContent = err.message;
            errorBox.style.display = "block";
          } finally {
            submitBtn.disabled = false;
          }
        });
      },
    });
  }

  function openDrinkModal(entry, onDone) {
    const html = `
      <button class="modal-close" data-close>&times;</button>
      <h2>Drink &mdash; ${escapeHtml(entry.beer.name)}</h2>
      <p class="subtle">${escapeHtml(entry.beer.brewery.name)}${entry.beer.style ? " &middot; " + escapeHtml(entry.beer.style) : ""}</p>
      <form data-drink-form>
        <div class="field-row">
          <div class="field">
            <label>Quantity</label>
            <input class="input" type="number" min="1" max="${entry.quantity}" step="1" name="quantity" value="1" required />
          </div>
          <div class="field">
            <label>Date</label>
            ${isoDateInputHtml("consumed_on", todayIsoLocal())}
          </div>
        </div>
        <div class="field">
          <label>Rating <span class="subtle">(optional)</span></label>
          ${starPicker("rating", 0)}
        </div>
        <div class="field">
          <label>Tasting note <span class="subtle">(optional)</span></label>
          <textarea class="input" name="note" placeholder="How was it?"></textarea>
        </div>
        <label class="checkbox-row">
          <input type="checkbox" name="delete_if_empty" ${entry.quantity <= 1 ? "checked" : ""} />
          Remove this cellar entry once it hits zero
        </label>
        <div class="form-error" data-error style="display:none"></div>
        <div class="form-actions">
          <button type="submit" class="btn btn-primary btn-block">Log it</button>
        </div>
      </form>
    `;
    openModal(html, {
      onMount(modalEl, close) {
        modalEl.querySelector("[data-close]").addEventListener("click", close);
        wireStarPicker(modalEl);
        wireIsoDateInputs(modalEl);
        const form = modalEl.querySelector("[data-drink-form]");
        const errorBox = modalEl.querySelector("[data-error]");
        form.addEventListener("submit", async (e) => {
          e.preventDefault();
          errorBox.style.display = "none";
          const fd = new FormData(form);
          const submitBtn = form.querySelector('button[type="submit"]');
          submitBtn.disabled = true;
          try {
            const consumedOn = fd.get("consumed_on")?.trim() || "";
            if (!isValidIsoDateOrEmpty(consumedOn)) throw new Error(`"${consumedOn}" isn't a valid date - use YYYY-MM-DD.`);
            const rating = Number(fd.get("rating") || 0);
            await Api.drinkEntry(entry.id, {
              quantity: Number(fd.get("quantity")),
              consumed_on: consumedOn || null,
              note: fd.get("note")?.trim() || null,
              rating: rating > 0 ? rating : null,
              delete_if_empty: fd.get("delete_if_empty") === "on",
            });
            close();
            toast("Cheers! Logged.");
            onDone();
          } catch (err) {
            errorBox.textContent = err.message;
            errorBox.style.display = "block";
          } finally {
            submitBtn.disabled = false;
          }
        });
      },
    });
  }

  function confirmDelete(message, onConfirm) {
    const html = `
      <button class="modal-close" data-close>&times;</button>
      <h2>Are you sure?</h2>
      <p>${escapeHtml(message)}</p>
      <div class="form-actions">
        <button class="btn btn-ghost btn-block" data-cancel>Cancel</button>
        <button class="btn btn-danger btn-block" data-confirm>Delete</button>
      </div>
    `;
    openModal(html, {
      onMount(modalEl, close) {
        modalEl.querySelector("[data-close]").addEventListener("click", close);
        modalEl.querySelector("[data-cancel]").addEventListener("click", close);
        modalEl.querySelector("[data-confirm]").addEventListener("click", async () => {
          close();
          await onConfirm();
        });
      },
    });
  }

  async function openWantedModal(account, onSaved) {
    const styles = await getBeerStyles();
    const html = `
      <button class="modal-close" data-close>&times;</button>
      <h2>Add to wanted list</h2>
      <p class="subtle">For a beer you don't have yet - it'll show on your public "Wanted" list, not your cellar count.</p>
      <form data-wanted-form>
        <div class="field suggest-wrap">
          <label>Beer</label>
          <input class="input" name="beer_search" autocomplete="off" placeholder="Start typing a beer name&hellip;" />
          <input type="hidden" name="beer_id" value="" />
          <div class="suggest-list" data-for="beer" style="display:none"></div>
          <div class="field-hint picked-note"></div>
        </div>
        <div class="field-row">
          <div class="field suggest-wrap">
            <label>Brewery</label>
            <input class="input" name="new_brewery_name" autocomplete="off" placeholder="Start typing a brewery name&hellip;" />
            <input type="hidden" name="brewery_id" value="" />
            <div class="suggest-list" data-for="brewery" style="display:none"></div>
          </div>
          <div class="field suggest-wrap">
            <label>Style <span class="subtle">(optional)</span></label>
            <input class="input" name="style" autocomplete="off" placeholder="Start typing a style&hellip;" />
            <div class="suggest-list" data-for="style" style="display:none"></div>
          </div>
        </div>
        <div class="field">
          <label>ABV % <span class="subtle">(optional)</span></label>
          <input class="input" type="number" step="0.1" min="0" max="100" name="abv" />
        </div>
        <div class="field">
          <label>Note <span class="subtle">(optional)</span></label>
          <textarea class="input" name="notes" placeholder="Which vintage, what you'd trade for it, etc."></textarea>
        </div>
        <div class="form-error" data-error style="display:none"></div>
        <div class="form-actions">
          <button type="submit" class="btn btn-primary btn-block">Add to wanted list</button>
        </div>
      </form>
    `;
    openModal(html, {
      onMount(modalEl, close) {
        modalEl.querySelector("[data-close]").addEventListener("click", close);
        wireBeerAutocomplete(modalEl, {});
        wireBreweryAutocomplete(modalEl);
        wireStyleAutocomplete(modalEl, styles);

        const form = modalEl.querySelector("[data-wanted-form]");
        const errorBox = modalEl.querySelector("[data-error]");
        form.addEventListener("submit", async (e) => {
          e.preventDefault();
          errorBox.style.display = "none";
          const fd = new FormData(form);
          const submitBtn = form.querySelector('button[type="submit"]');
          submitBtn.disabled = true;
          try {
            const beerId = fd.get("beer_id");
            const payload = { notes: fd.get("notes")?.trim() || null };
            if (beerId) {
              payload.beer_id = Number(beerId);
            } else {
              const name = fd.get("beer_search")?.trim();
              if (!name) throw new Error("Enter a beer name.");
              const pickedBreweryId = fd.get("brewery_id");
              payload.beer = {
                name,
                brewery_id: pickedBreweryId ? Number(pickedBreweryId) : null,
                new_brewery_name: pickedBreweryId ? null : fd.get("new_brewery_name")?.trim() || null,
                style: fd.get("style")?.trim() || null,
                abv: fd.get("abv") ? Number(fd.get("abv")) : null,
              };
              if (!payload.beer.brewery_id && !payload.beer.new_brewery_name) throw new Error("Enter a brewery name.");
            }
            await Api.addWanted(payload);
            close();
            toast("Added to your wanted list.");
            onSaved();
          } catch (err) {
            errorBox.textContent = err.message;
            errorBox.style.display = "block";
          } finally {
            submitBtn.disabled = false;
          }
        });
      },
    });
  }

  // ---------- Entry card rendering (used by the cellar dashboard + public view) ----------

  function badgeForLocation(entry, account) {
    if (!account.show_fridge_column) return "";
    return entry.location === "fridge"
      ? `<span class="badge badge-fridge">Fridge</span>`
      : `<span class="badge badge-cellar">Cellar</span>`;
  }

  function badgeForTrade(entry) {
    if (entry.trade_status === "ft") return `<span class="badge badge-ft">For Trade</span>`;
    if (entry.trade_status === "iso") {
      return entry.quantity === 0
        ? `<span class="badge badge-iso">Wanted</span>`
        : `<span class="badge badge-iso">ISO</span>`;
    }
    return "";
  }

  function entryCardHtml(entry, account, { editable }) {
    const metaBits = [];
    if (entry.beer.style) metaBits.push(escapeHtml(entry.beer.style));
    if (entry.beer.abv !== null && entry.beer.abv !== undefined) metaBits.push(`${entry.beer.abv}% ABV`);
    if (entry.size_oz) metaBits.push(`${ozToDisplay(entry.size_oz, account.unit_system)} ${volumeUnitLabel(account.unit_system)}`);
    if (entry.custom_location) metaBits.push(escapeHtml(entry.custom_location));
    if (entry.best_before) metaBits.push(`Best before ${fmtDate(entry.best_before)}`);

    const isWantedOnly = entry.quantity === 0 && entry.trade_status === "iso";

    const actions = editable
      ? `<div class="entry-actions">
           <div class="row">
             <button class="btn btn-icon" data-act="add" title="Add one to stock">&plus;1</button>
             <button class="btn btn-ghost btn-sm" data-act="drink">Drink</button>
           </div>
           <div class="row">
             ${
               account.show_fridge_column
                 ? `<button class="btn btn-icon" data-act="move" title="Move to ${
                     entry.location === "fridge" ? "cellar" : "fridge"
                   }">${entry.location === "fridge" ? "&#8594;Cellar" : "&#8594;Fridge"}</button>`
                 : ""
             }
             <button class="btn btn-icon" data-act="edit" title="Edit">Edit</button>
             <button class="btn btn-icon" data-act="delete" title="Delete">Del</button>
           </div>
         </div>`
      : "";

    return `
      <div class="entry-card" data-entry-id="${entry.id}">
        <div class="entry-main">
          <h3>${escapeHtml(entry.beer.name)}</h3>
          <div class="entry-meta">
            <span>${escapeHtml(entry.beer.brewery.name)}</span>
            ${metaBits.map((m) => `<span class="dot">&middot;</span><span>${m}</span>`).join("")}
            ${badgeForLocation(entry, account)}
            ${badgeForTrade(entry)}
          </div>
          ${isWantedOnly ? "" : tally(entry.quantity)}
        </div>
        ${actions}
        ${entry.batch_notes ? `<div class="entry-notes">${escapeHtml(entry.batch_notes)}</div>` : ""}
      </div>
    `;
  }

  function wireEntryCards(root, entries, account, reload) {
    root.querySelectorAll("[data-entry-id]").forEach((card) => {
      const id = Number(card.dataset.entryId);
      const entry = entries.find((e) => e.id === id);
      if (!entry) return;

      const addBtn = card.querySelector('[data-act="add"]');
      if (addBtn)
        addBtn.addEventListener("click", async () => {
          addBtn.disabled = true;
          try {
            await Api.patchEntry(id, { quantity: entry.quantity + 1 });
            toast("Added one bottle.");
            reload();
          } catch (e) {
            toast(e.message, "error");
          } finally {
            addBtn.disabled = false;
          }
        });

      const drinkBtn = card.querySelector('[data-act="drink"]');
      if (drinkBtn)
        drinkBtn.addEventListener("click", () => {
          if (entry.quantity < 1) {
            toast("Nothing left to drink.", "error");
            return;
          }
          openDrinkModal(entry, reload);
        });

      const moveBtn = card.querySelector('[data-act="move"]');
      if (moveBtn)
        moveBtn.addEventListener("click", async () => {
          const to = entry.location === "fridge" ? "cellar" : "fridge";
          try {
            await Api.moveEntry(id, to);
            toast(`Moved to ${to === "fridge" ? "the fridge" : "the cellar"}.`);
            reload();
          } catch (e) {
            toast(e.message, "error");
          }
        });

      const editBtn = card.querySelector('[data-act="edit"]');
      if (editBtn) editBtn.addEventListener("click", () => openEntryModal(entry, account, reload));

      const delBtn = card.querySelector('[data-act="delete"]');
      if (delBtn)
        delBtn.addEventListener("click", () => {
          confirmDelete(`Remove ${entry.beer.name} from your cellar? This won't erase past tasting notes.`, async () => {
            try {
              await Api.deleteEntry(id);
              toast("Removed.");
              reload();
            } catch (e) {
              toast(e.message, "error");
            }
          });
        });
    });
  }

  // ---------- Pages ----------

  async function home(root, ctx) {
    root.innerHTML = `
      <div class="hero">
        <h1>Keep count of what's <span class="glow">aging in the dark</span>.</h1>
        <p class="lede">A self-hosted tracker for your cellar and fridge &mdash; bottles, batches, tasting notes, and who's willing to trade.</p>
        <div class="hero-actions" id="hero-actions"></div>
      </div>
      <div class="section-label">Recently uncorked</div>
      <div class="feed-list" id="feed">${spinnerHtml()}</div>
    `;
    const heroActions = root.querySelector("#hero-actions");
    if (ctx.user) {
      heroActions.innerHTML = `<a class="btn btn-primary" href="#/cellar">Go to my cellar</a>
        <a class="btn btn-ghost" href="#/browse">Browse cellars</a>`;
    } else {
      heroActions.innerHTML = `<a class="btn btn-primary" href="#/register">Create an account</a>
        <a class="btn btn-ghost" href="#/login">Log in</a>`;
    }
    try {
      const recent = await Api.recentActivity();
      const feed = root.querySelector("#feed");
      if (!recent.length) {
        feed.innerHTML = `<div class="empty-note">Nothing logged yet &mdash; be the first to crack one open.</div>`;
      } else {
        feed.innerHTML = recent
          .map(
            (r) => `<div class="feed-row">
              <span class="who">${escapeHtml(firstName(r.display_name) || r.username)}</span>
              <span class="what">drank ${escapeHtml(r.beer_name)} <span class="subtle">(${escapeHtml(r.brewery_name)})</span></span>
              <span class="meta">${fmtDate(r.consumed_on)}</span>
            </div>`
          )
          .join("");
      }
    } catch (e) {
      root.querySelector("#feed").innerHTML = `<div class="empty-note">Couldn't load recent activity.</div>`;
    }
  }

  function spinnerHtml() {
    return `<div class="spinner"></div>`;
  }

  function authForm({ title, submitLabel, fields, switchHtml, extraHtml }) {
    return `
      <div class="auth-shell panel">
        <h1>${title}</h1>
        <form data-auth-form>
          ${fields}
          <div class="form-error" data-error style="display:none"></div>
          <div class="form-actions">
            <button type="submit" class="btn btn-primary btn-block">${submitLabel}</button>
          </div>
        </form>
        ${extraHtml || ""}
        <div class="auth-switch">${switchHtml || ""}</div>
      </div>
    `;
  }

  function ssoBlockHtml(authConfig, { withDivider }) {
    if (!authConfig.oidc_enabled) return "";
    return `
      ${withDivider ? `<div class="auth-divider"><span>or</span></div>` : ""}
      <a class="btn btn-ghost btn-block" href="/api/auth/oidc/login">${escapeHtml(authConfig.oidc_button_label)}</a>
    `;
  }

  function login(root, ctx, query) {
    const cfg = ctx.authConfig;
    const oidcError = query && query.get("oidc_error");
    const errorBanner = oidcError
      ? `<div class="form-error" style="margin-bottom:16px">SSO sign-in failed: ${escapeHtml(oidcError)}</div>`
      : "";

    if (!cfg.password_auth_enabled && !cfg.oidc_enabled) {
      root.innerHTML = `
        <div class="auth-shell panel">
          <h1>Sign-in unavailable</h1>
          ${errorBanner}
          <p>This instance doesn't have a login method configured yet. Ask whoever runs it to enable password login or SSO.</p>
        </div>
      `;
      return;
    }

    if (!cfg.password_auth_enabled) {
      root.innerHTML = `
        <div class="auth-shell panel">
          <h1>Welcome back</h1>
          ${errorBanner}
          <p class="subtle">Password sign-in is disabled on this instance.</p>
          ${ssoBlockHtml(cfg, { withDivider: false })}
        </div>
      `;
      return;
    }

    root.innerHTML = authForm({
      title: "Welcome back",
      submitLabel: "Log in",
      fields: `
        ${errorBanner}
        <div class="field"><label>Username</label><input class="input" name="username" required autofocus /></div>
        <div class="field">
          <label>Password</label>
          <input class="input" type="password" name="password" required />
          ${cfg.smtp_enabled ? `<div class="field-hint"><a href="#/forgot-password">Forgot password?</a></div>` : ""}
        </div>
      `,
      extraHtml: ssoBlockHtml(cfg, { withDivider: true }),
      switchHtml: cfg.registration_enabled ? `Don't have a cellar yet? <a href="#/register">Create one</a>` : "",
    });
    const form = root.querySelector("[data-auth-form]");
    const errorBox = root.querySelector("[data-error]");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      errorBox.style.display = "none";
      const fd = new FormData(form);
      try {
        const { access_token } = await Api.login(fd.get("username"), fd.get("password"));
        Api.setToken(access_token);
        await ctx.refreshUser();
        toast(`Welcome back, ${fd.get("username")}.`);
        location.hash = "#/cellar";
      } catch (err) {
        errorBox.textContent = err.message;
        errorBox.style.display = "block";
      }
    });
  }

  function register(root, ctx) {
    if (!ctx.authConfig.password_auth_enabled || !ctx.authConfig.registration_enabled) {
      location.hash = "#/login";
      return;
    }
    root.innerHTML = authForm({
      title: "Set up your cellar",
      submitLabel: "Create account",
      fields: `
        <div class="field"><label>Username</label><input class="input" name="username" pattern="[a-zA-Z0-9_\\-]{3,32}" required autofocus /></div>
        <div class="field"><label>Email</label><input class="input" type="email" name="email" required /></div>
        <div class="field"><label>Password</label><input class="input" type="password" name="password" minlength="8" required /></div>
        <div class="field-hint">At least 8 characters.</div>
      `,
      extraHtml: ssoBlockHtml(ctx.authConfig, { withDivider: true }),
      switchHtml: `Already have an account? <a href="#/login">Log in</a>`,
    });
    const form = root.querySelector("[data-auth-form]");
    const errorBox = root.querySelector("[data-error]");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      errorBox.style.display = "none";
      const fd = new FormData(form);
      try {
        const { access_token } = await Api.register(fd.get("username"), fd.get("email"), fd.get("password"));
        Api.setToken(access_token);
        await ctx.refreshUser();
        toast("Cellar created. Welcome!");
        location.hash = "#/cellar";
      } catch (err) {
        errorBox.textContent = err.message;
        errorBox.style.display = "block";
      }
    });
  }

  function forgotPassword(root, ctx) {
    if (!ctx.authConfig.password_auth_enabled || !ctx.authConfig.smtp_enabled) {
      location.hash = "#/login";
      return;
    }
    root.innerHTML = authForm({
      title: "Reset your password",
      submitLabel: "Send reset link",
      fields: `
        <p class="subtle" style="margin-top:0">Enter the email on your account and we'll send a link to set a new password.</p>
        <div class="field"><label>Email</label><input class="input" type="email" name="email" required autofocus /></div>
      `,
      switchHtml: `<a href="#/login">Back to login</a>`,
    });
    const form = root.querySelector("[data-auth-form]");
    const errorBox = root.querySelector("[data-error]");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      errorBox.style.display = "none";
      const fd = new FormData(form);
      const submitBtn = form.querySelector('button[type="submit"]');
      submitBtn.disabled = true;
      try {
        await Api.forgotPassword(fd.get("email"));
        root.innerHTML = `
          <div class="auth-shell panel">
            <h1>Check your email</h1>
            <p>If that email is registered here, a reset link is on its way. It's valid for one hour.</p>
            <div class="auth-switch"><a href="#/login">Back to login</a></div>
          </div>
        `;
      } catch (err) {
        errorBox.textContent = err.message;
        errorBox.style.display = "block";
        submitBtn.disabled = false;
      }
    });
  }

  function resetPassword(root, ctx, query) {
    const token = query && query.get("token");
    if (!token) {
      root.innerHTML = `
        <div class="auth-shell panel">
          <h1>Invalid link</h1>
          <p>This password reset link is missing its token. Request a new one from the login page.</p>
          <div class="auth-switch"><a href="#/forgot-password">Request a new link</a></div>
        </div>
      `;
      return;
    }
    root.innerHTML = authForm({
      title: "Set a new password",
      submitLabel: "Set password",
      fields: `
        <div class="field">
          <label>New password</label>
          <input class="input" type="password" name="new_password" minlength="8" required autofocus />
          <div class="field-hint">At least 8 characters.</div>
        </div>
      `,
      switchHtml: `<a href="#/login">Back to login</a>`,
    });
    const form = root.querySelector("[data-auth-form]");
    const errorBox = root.querySelector("[data-error]");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      errorBox.style.display = "none";
      const fd = new FormData(form);
      const submitBtn = form.querySelector('button[type="submit"]');
      submitBtn.disabled = true;
      try {
        const { access_token } = await Api.resetPassword(token, fd.get("new_password"));
        Api.setToken(access_token);
        await ctx.refreshUser();
        toast("Password set. You're logged in.");
        location.hash = "#/cellar";
      } catch (err) {
        errorBox.textContent = err.message;
        errorBox.style.display = "block";
        submitBtn.disabled = false;
      }
    });
  }

  async function cellar(root, ctx) {
    if (!ctx.user) {
      location.hash = "#/login";
      return;
    }
    let sort = ctx.account.default_sort;
    let sortDirection = "asc";
    let locationFilter = null;
    // Purely a display preference, not account data - same treatment as
    // the theme setting, which also lives in localStorage rather than
    // the account record.
    let viewMode = localStorage.getItem("cellar_view_mode") === "compact" ? "compact" : "comfortable";

    const sortLabels = { beer: "By beer", brewery: "By brewery", drinkby: "By drink-by date" };
    const sortArrow = () => (sortDirection === "asc" ? "↑" : "↓");
    const sortButtonHtml = (val) =>
      `<button data-val="${val}" class="${sort === val ? "active" : ""}">${escapeHtml(sortLabels[val])}${
        sort === val ? ` ${sortArrow()}` : ""
      }</button>`;

    root.innerHTML = `
      <div class="page-head">
        <h1>My cellar <span class="subtle" style="font-size:14px; font-weight:400;" id="cellar-total"></span></h1>
        <div style="display:flex; gap:8px;">
          ${ctx.account.trading_enabled ? `<button class="btn btn-ghost" id="add-wanted">+ Add to wanted list</button>` : ""}
          <button class="btn btn-primary" id="add-bottle">+ Add a bottle</button>
        </div>
      </div>
      <div class="toolbar">
        <div class="seg" data-sort>
          ${sortButtonHtml("beer")}
          ${sortButtonHtml("brewery")}
          ${sortButtonHtml("drinkby")}
        </div>
        ${
          ctx.account.show_fridge_column
            ? `<div class="seg" data-loc>
                 <button data-val="" class="active">All</button>
                 <button data-val="cellar">Cellar</button>
                 <button data-val="fridge">Fridge</button>
               </div>`
            : ""
        }
        <div class="seg" data-view>
          <button data-val="comfortable" class="${viewMode === "comfortable" ? "active" : ""}">Comfortable</button>
          <button data-val="compact" class="${viewMode === "compact" ? "active" : ""}">Compact</button>
        </div>
        <div class="spacer"></div>
        ${ctx.account.trading_enabled ? `<a class="btn btn-ghost btn-sm" href="#/u/${encodeURIComponent(ctx.user)}/trades">Trade list</a>` : ""}
        <a class="btn btn-ghost btn-sm" href="#/consumed">History</a>
        <a class="btn btn-ghost btn-sm" href="#/import-export">Import/Export</a>
      </div>
      <div id="entries">${spinnerHtml()}</div>
    `;

    root.querySelector("#add-bottle").addEventListener("click", () => {
      openEntryModal(null, ctx.account, load);
    });
    const addWantedBtn = root.querySelector("#add-wanted");
    if (addWantedBtn) {
      addWantedBtn.addEventListener("click", () => {
        openWantedModal(ctx.account, load);
      });
    }

    function refreshSortButtons() {
      root.querySelectorAll("[data-sort] button").forEach((b) => {
        const val = b.dataset.val;
        const isActive = val === sort;
        b.classList.toggle("active", isActive);
        b.textContent = isActive ? `${sortLabels[val]} ${sortArrow()}` : sortLabels[val];
      });
    }

    root.querySelectorAll("[data-sort] button").forEach((btn) => {
      btn.addEventListener("click", () => {
        const val = btn.dataset.val;
        // Clicking the already-active sort flips direction; picking a
        // different one starts fresh at ascending, like most sortable
        // tables/lists do.
        if (val === sort) {
          sortDirection = sortDirection === "asc" ? "desc" : "asc";
        } else {
          sort = val;
          sortDirection = "asc";
        }
        refreshSortButtons();
        load();
      });
    });
    const locSeg = root.querySelector("[data-loc]");
    if (locSeg) {
      locSeg.querySelectorAll("button").forEach((btn) => {
        btn.addEventListener("click", () => {
          locationFilter = btn.dataset.val || null;
          locSeg.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b === btn));
          load();
        });
      });
    }
    root.querySelectorAll("[data-view] button").forEach((btn) => {
      btn.addEventListener("click", () => {
        viewMode = btn.dataset.val;
        localStorage.setItem("cellar_view_mode", viewMode);
        root.querySelectorAll("[data-view] button").forEach((b) => b.classList.toggle("active", b === btn));
        const list = root.querySelector(".entry-list");
        if (list) list.classList.toggle("compact", viewMode === "compact");
      });
    });

    async function load() {
      const container = root.querySelector("#entries");
      const totalEl = root.querySelector("#cellar-total");
      container.innerHTML = spinnerHtml();
      try {
        const entries = await Api.listCellar(sort, locationFilter, sortDirection);
        if (!entries.length) {
          container.innerHTML = `<div class="panel empty-note">Your cellar's empty. Add your first bottle to start tracking it.</div>`;
          if (totalEl) totalEl.textContent = "";
          return;
        }
        container.innerHTML = `<div class="entry-list${viewMode === "compact" ? " compact" : ""}">${entries
          .map((e) => entryCardHtml(e, ctx.account, { editable: true }))
          .join("")}</div>`;
        wireEntryCards(container, entries, ctx.account, load);
        if (totalEl) {
          const totalBottles = entries.reduce((sum, e) => sum + e.quantity, 0);
          totalEl.textContent = `${entries.length} beer${entries.length === 1 ? "" : "s"} \u00b7 ${totalBottles} on hand`;
        }
      } catch (e) {
        container.innerHTML = `<div class="panel empty-note">Couldn't load your cellar: ${escapeHtml(e.message)}</div>`;
        if (totalEl) totalEl.textContent = "";
      }
    }
    load();
  }

  async function account(root, ctx) {
    if (!ctx.user) {
      location.hash = "#/login";
      return;
    }
    const a = ctx.account;
    root.innerHTML = `
      <div class="page-head"><h1>Account</h1></div>

      <div class="panel" style="margin-bottom:20px">
        <h3>Signed in as ${escapeHtml(firstName(a.display_name) || a.username)}</h3>
        <p class="subtle">${escapeHtml(a.username)} &middot; ${escapeHtml(a.email)}</p>
      </div>

      <div class="panel" style="margin-bottom:20px">
        <h3>Cellar preferences</h3>
        <div class="settings-grid">
          ${selectRow(
            "default_sort",
            "Default sort order",
            "How your cellar list sorts by default. You can still switch it temporarily from the cellar page.",
            [
              { value: "beer", label: "By beer" },
              { value: "brewery", label: "By brewery" },
              { value: "drinkby", label: "By drink-by date" },
            ],
            a.default_sort
          )}
          ${toggleRow("unit_metric", "Use metric units", "Show and enter bottle sizes in millilitres (mL) instead of fluid ounces (oz).", a.unit_system === "metric")}
          ${toggleRow("show_fridge_column", "Track a separate fridge", "Turn off if you only track one shelf.", a.show_fridge_column)}
          ${toggleRow("show_location_column", "Track custom shelf / location", "Adds a free-text location field to each bottle.", a.show_location_column)}
          ${toggleRow("trading_enabled", "Enable trading labels", "Mark bottles as For Trade or In Search Of, and track beers you don't have yet on a wanted list.", a.trading_enabled)}
        </div>
      </div>

      ${
        a.trading_enabled
          ? `<div class="panel" style="margin-bottom:20px">
              <h3>Your trade list</h3>
              <p class="subtle">Shareable with anyone, no account or login needed - independent of whether your full cellar is public.</p>
              <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
                <input class="input" readonly value="${escapeHtml(location.origin + "/#/u/" + a.username + "/trades")}" style="flex:1; min-width:220px" id="trade-link-input" />
                <button class="btn btn-ghost btn-sm" id="copy-trade-link">Copy link</button>
                <a class="btn btn-ghost btn-sm" href="#/u/${encodeURIComponent(a.username)}/trades" target="_blank" rel="noopener">Preview</a>
              </div>
            </div>`
          : ""
      }

      <div class="panel" style="margin-bottom:20px">
        <h3>Privacy</h3>
        <div class="settings-grid">
          ${toggleRow("cellar_public", "Make my cellar public", "Others can find you via Browse cellars and view your bottles.", a.cellar_public)}
          ${toggleRow("notes_public", "Show my tasting notes publicly", "Only applies if your cellar is public.", a.notes_public)}
          ${toggleRow("drinkby_public", "Show best-before dates publicly", "Only applies if your cellar is public.", a.drinkby_public)}
        </div>
      </div>

      ${
        ctx.authConfig.password_auth_enabled
          ? `<div class="panel">
              <h3>Change password</h3>
              <form data-pw-form>
                <div class="field"><label>Current password</label><input class="input" type="password" name="current_password" required /></div>
                <div class="field"><label>New password</label><input class="input" type="password" name="new_password" minlength="8" required /></div>
                <div class="form-error" data-pw-error style="display:none"></div>
                <button type="submit" class="btn btn-ghost">Update password</button>
              </form>
            </div>`
          : `<div class="panel">
              <h3>Password sign-in</h3>
              <p class="subtle">Password-based sign-in is disabled on this instance. Manage your login through your SSO provider instead.</p>
            </div>`
      }
    `;

    root.querySelectorAll("[data-toggle]").forEach((input) => {
      input.addEventListener("change", async () => {
        const key = input.dataset.toggle;
        const payload = {};
        if (key === "unit_metric") {
          payload.unit_system = input.checked ? "metric" : "imperial";
        } else {
          payload[key] = input.checked;
        }
        try {
          const updated = await Api.patchAccount(payload);
          Object.assign(ctx.account, updated);
          toast("Saved.");
          if (key === "trading_enabled") {
            account(root, ctx); // re-render so the trade-list share panel appears/disappears immediately
            return;
          }
        } catch (e) {
          toast(e.message, "error");
          input.checked = !input.checked;
        }
      });
    });

    root.querySelectorAll("[data-select]").forEach((select) => {
      select.addEventListener("change", async () => {
        const key = select.dataset.select;
        const previous = ctx.account[key];
        try {
          const updated = await Api.patchAccount({ [key]: select.value });
          Object.assign(ctx.account, updated);
          toast("Saved.");
        } catch (e) {
          toast(e.message, "error");
          select.value = previous;
        }
      });
    });

    const copyTradeLinkBtn = root.querySelector("#copy-trade-link");
    if (copyTradeLinkBtn) {
      copyTradeLinkBtn.addEventListener("click", async () => {
        const linkInput = root.querySelector("#trade-link-input");
        try {
          await navigator.clipboard.writeText(linkInput.value);
          toast("Link copied.");
        } catch (e) {
          linkInput.select();
          toast("Press Ctrl/Cmd+C to copy.", "error");
        }
      });
    }

    const pwForm = root.querySelector("[data-pw-form]");
    if (pwForm) {
      const pwError = root.querySelector("[data-pw-error]");
      pwForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        pwError.style.display = "none";
        const fd = new FormData(pwForm);
        try {
          const { access_token } = await Api.changePassword(fd.get("current_password"), fd.get("new_password"));
          Api.setToken(access_token);
          toast("Password updated.");
          pwForm.reset();
        } catch (err) {
          pwError.textContent = err.message;
          pwError.style.display = "block";
        }
      });
    }
  }

  function toggleRow(key, label, desc, checked) {
    return `
      <div class="toggle-row">
        <div>
          <div class="label">${label}</div>
          <div class="desc">${desc}</div>
        </div>
        <label class="switch">
          <input type="checkbox" data-toggle="${key}" ${checked ? "checked" : ""} />
          <span class="track"></span>
          <span class="thumb"></span>
        </label>
      </div>
    `;
  }

  function selectRow(key, label, desc, options, value) {
    return `
      <div class="toggle-row">
        <div>
          <div class="label">${label}</div>
          <div class="desc">${desc}</div>
        </div>
        <select class="input" data-select="${key}" style="width:auto; flex-shrink:0;">
          ${options
            .map((o) => `<option value="${o.value}" ${o.value === value ? "selected" : ""}>${escapeHtml(o.label)}</option>`)
            .join("")}
        </select>
      </div>
    `;
  }

  async function browse(root) {
    root.innerHTML = `<div class="page-head"><h1>Browse cellars</h1></div><div id="list">${spinnerHtml()}</div>`;
    try {
      const users = await Api.browseCellars();
      const list = root.querySelector("#list");
      if (!users.length) {
        list.innerHTML = `<div class="panel empty-note">No public cellars yet.</div>`;
        return;
      }
      list.innerHTML = `<div class="user-list">${users
        .map(
          (u) => `<a class="user-row" href="#/u/${encodeURIComponent(u.username)}">
            <span class="name">${escapeHtml(firstName(u.display_name) || u.username)}</span>
            <span class="stat">${u.cellar_count} bottle${u.cellar_count === 1 ? "" : "s"}${
            u.trading_enabled ? " &middot; trades" : ""
          }</span>
          </a>`
        )
        .join("")}</div>`;
    } catch (e) {
      root.querySelector("#list").innerHTML = `<div class="panel empty-note">Couldn't load the directory.</div>`;
    }
  }

  async function publicCellar(root, username, ctx) {
    root.innerHTML = spinnerHtml();
    let data;
    try {
      data = await Api.publicCellar(username);
    } catch (e) {
      root.innerHTML = `<div class="page-head"><h1>Not found</h1></div><div class="panel empty-note">${escapeHtml(
        e.message
      )}</div>`;
      return;
    }
    const fakeAccount = {
      show_fridge_column: true,
      trading_enabled: data.trading_enabled,
      unit_system: (ctx && ctx.account && ctx.account.unit_system) || "metric",
    };
    root.innerHTML = `
      <div class="page-head">
        <h1>${escapeHtml(firstName(data.display_name) || data.username)}'s cellar</h1>
        <span class="subtle">${data.total_consumed} bottle${data.total_consumed === 1 ? "" : "s"} logged all-time</span>
      </div>
      <div class="tabs">
        <button class="active" data-tab="bottles">Bottles (${data.entries.length})</button>
        <button data-tab="notes">Tasting notes (${data.tasting_notes.length})</button>
      </div>
      <div data-pane="bottles">
        ${
          data.entries.length
            ? `<div class="entry-list">${data.entries
                .map((e) => entryCardHtml(e, fakeAccount, { editable: false }))
                .join("")}</div>`
            : `<div class="panel empty-note">Nothing on the shelf right now.</div>`
        }
      </div>
      <div data-pane="notes" style="display:none">
        ${
          data.tasting_notes.length
            ? `<div class="feed-list">${data.tasting_notes
                .map(
                  (n) => `<div class="feed-row" style="display:block">
                    <div><span class="what"><strong>${escapeHtml(n.beer_name)}</strong> &mdash; ${escapeHtml(
                    n.brewery_name
                  )}</span> <span class="meta">${fmtDate(n.consumed_on)}</span></div>
                    ${n.rating ? `<div>${starsReadonly(n.rating)}</div>` : ""}
                    <div class="subtle">${escapeHtml(n.note)}</div>
                  </div>`
                )
                .join("")}</div>`
            : `<div class="panel empty-note">No public tasting notes.</div>`
        }
      </div>
    `;
    root.querySelectorAll("[data-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        root.querySelectorAll("[data-tab]").forEach((b) => b.classList.toggle("active", b === btn));
        root.querySelectorAll("[data-pane]").forEach((p) => {
          p.style.display = p.dataset.pane === btn.dataset.tab ? "block" : "none";
        });
      });
    });
  }

  function tradeCardHtml(item, kind, showDelete) {
    // kind: "ft" | "wanted". Wanted items are further distinguished by
    // item.owned: true means "have some already, want more" (came from a
    // cellar entry marked ISO), false means "don't have any yet" (came
    // from the separate wanted list). showDelete only applies to the
    // latter - the only kind manageable from this page.
    const metaBits = [];
    if (item.beer.style) metaBits.push(escapeHtml(item.beer.style));
    if (item.beer.abv !== null && item.beer.abv !== undefined) metaBits.push(`${item.beer.abv}% ABV`);

    let badge = `<span class="badge badge-ft">For Trade</span>`;
    if (kind === "wanted") {
      badge = item.owned
        ? `<span class="badge badge-iso">Have some, want more</span>`
        : `<span class="badge badge-iso">Wanted</span>`;
    }
    const notes = kind === "ft" ? item.batch_notes : item.notes;
    const canDelete = showDelete && kind === "wanted" && !item.owned;

    return `
      <div class="entry-card">
        <div class="entry-main">
          <h3>${escapeHtml(item.beer.name)}</h3>
          <div class="entry-meta">
            <span>${escapeHtml(item.beer.brewery.name)}</span>
            ${metaBits.map((m) => `<span class="dot">&middot;</span><span>${m}</span>`).join("")}
            ${badge}
          </div>
          ${kind === "ft" ? tally(item.quantity) : ""}
        </div>
        ${
          canDelete
            ? `<div class="entry-actions"><div class="row"><button class="btn btn-icon" data-del-wanted="${String(
                item.id
              ).replace(/^wanted-/, "")}" title="Remove from wanted list">Del</button></div></div>`
            : ""
        }
        ${notes ? `<div class="entry-notes">${escapeHtml(notes)}</div>` : ""}
      </div>
    `;
  }

  async function publicTrades(root, username, ctx) {
    root.innerHTML = spinnerHtml();
    let data;
    try {
      data = await Api.publicTrades(username);
    } catch (e) {
      root.innerHTML = `<div class="page-head"><h1>Not found</h1></div><div class="panel empty-note">${escapeHtml(
        e.message
      )}</div>`;
      return;
    }

    const isSelf = !!(ctx && ctx.user && ctx.user === data.username);
    const shareUrl = `${location.origin}${location.pathname}#/u/${encodeURIComponent(data.username)}/trades`;

    function render() {
      root.innerHTML = `
        <div class="page-head">
          <h1>${escapeHtml(firstName(data.display_name) || data.username)}'s trade list</h1>
          ${isSelf ? `<button class="btn btn-primary btn-sm" id="add-wanted-here">+ Add to wanted list</button>` : ""}
        </div>
        ${
          isSelf
            ? `<div class="panel" style="margin-bottom:20px">
                 <div class="field-hint" style="margin-bottom:6px">Share this link so people can see it without logging in:</div>
                 <input class="input" readonly value="${escapeHtml(shareUrl)}" data-select-on-click />
               </div>`
            : ""
        }
        <div class="section-label">For Trade (${data.for_trade.length})</div>
        ${
          data.for_trade.length
            ? `<div class="entry-list">${data.for_trade.map((e) => tradeCardHtml(e, "ft")).join("")}</div>`
            : `<div class="panel empty-note">Nothing up for trade right now.</div>`
        }
        <div class="section-label">Wanted (${data.wanted.length})</div>
        ${
          data.wanted.length
            ? `<div class="entry-list">${data.wanted.map((e) => tradeCardHtml(e, "wanted", isSelf)).join("")}</div>`
            : `<div class="panel empty-note">Nothing on the wanted list right now.</div>`
        }
      `;

      if (!isSelf) return;

      const shareInput = root.querySelector("[data-select-on-click]");
      if (shareInput) shareInput.addEventListener("click", () => shareInput.select());

      root.querySelector("#add-wanted-here").addEventListener("click", () => {
        openWantedModal(ctx.account, async () => {
          data = await Api.publicTrades(username);
          render();
        });
      });
      root.querySelectorAll("[data-del-wanted]").forEach((btn) => {
        btn.addEventListener("click", () => {
          confirmDelete("Remove this from your wanted list?", async () => {
            try {
              await Api.deleteWanted(Number(btn.dataset.delWanted));
              toast("Removed.");
              data = await Api.publicTrades(username);
              render();
            } catch (e) {
              toast(e.message, "error");
            }
          });
        });
      });
    }

    render();
  }

  function openBreweryModal(brewery, onSaved) {
    const isEdit = !!brewery;
    const html = `
      <button class="modal-close" data-close>&times;</button>
      <h2>${isEdit ? "Edit brewery" : "Add a brewery"}</h2>
      <form data-brewery-form>
        <div class="field">
          <label>Name</label>
          <input class="input" name="name" value="${escapeHtml(brewery?.name || "")}" required />
        </div>
        <div class="field">
          <label>Website <span class="subtle">(optional)</span></label>
          <input class="input" type="url" name="website" value="${escapeHtml(brewery?.website || "")}" placeholder="https://..." />
        </div>
        <div class="form-error" data-error style="display:none"></div>
        <div class="form-actions">
          <button type="submit" class="btn btn-primary btn-block">${isEdit ? "Save changes" : "Add brewery"}</button>
        </div>
      </form>
    `;
    openModal(html, {
      onMount(modalEl, close) {
        modalEl.querySelector("[data-close]").addEventListener("click", close);
        const form = modalEl.querySelector("[data-brewery-form]");
        const errorBox = modalEl.querySelector("[data-error]");
        form.addEventListener("submit", async (e) => {
          e.preventDefault();
          errorBox.style.display = "none";
          const fd = new FormData(form);
          const submitBtn = form.querySelector('button[type="submit"]');
          submitBtn.disabled = true;
          try {
            const payload = {
              name: fd.get("name").trim(),
              website: fd.get("website")?.trim() || null,
            };
            if (isEdit) {
              await Api.adminPatchBrewery(brewery.id, payload);
            } else {
              await Api.adminCreateBrewery(payload);
            }
            close();
            toast(isEdit ? "Brewery updated." : "Brewery added.");
            onSaved();
          } catch (err) {
            errorBox.textContent = err.message;
            errorBox.style.display = "block";
          } finally {
            submitBtn.disabled = false;
          }
        });
      },
    });
  }

  function openEditLogModal(log, onDone) {
    const html = `
      <button class="modal-close" data-close>&times;</button>
      <h2>Edit &mdash; ${escapeHtml(log.beer.name)}</h2>
      <p class="subtle">${escapeHtml(log.beer.brewery.name)}</p>
      <form data-edit-log-form>
        <div class="field-row">
          <div class="field">
            <label>Quantity</label>
            <input class="input" type="number" min="1" step="1" name="quantity" value="${log.quantity}" required />
          </div>
          <div class="field">
            <label>Date</label>
            ${isoDateInputHtml("consumed_on", log.consumed_on)}
          </div>
        </div>
        <div class="field">
          <label>Rating <span class="subtle">(optional)</span></label>
          ${starPicker("rating", log.rating || 0)}
        </div>
        <div class="field">
          <label>Tasting note <span class="subtle">(optional)</span></label>
          <textarea class="input" name="note" placeholder="How was it?">${escapeHtml(log.note || "")}</textarea>
        </div>
        <div class="form-error" data-error style="display:none"></div>
        <div class="form-actions">
          <button type="submit" class="btn btn-primary btn-block">Save changes</button>
        </div>
      </form>
    `;
    openModal(html, {
      onMount(modalEl, close) {
        modalEl.querySelector("[data-close]").addEventListener("click", close);
        wireStarPicker(modalEl);
        wireIsoDateInputs(modalEl);
        const form = modalEl.querySelector("[data-edit-log-form]");
        const errorBox = modalEl.querySelector("[data-error]");
        form.addEventListener("submit", async (e) => {
          e.preventDefault();
          errorBox.style.display = "none";
          const fd = new FormData(form);
          const submitBtn = form.querySelector('button[type="submit"]');
          submitBtn.disabled = true;
          try {
            const consumedOn = fd.get("consumed_on")?.trim() || "";
            // Unlike logging a fresh drink, empty here can't just fall back
            // to "today" server-side - it's editing a date that already
            // has to exist, so an empty field is a validation error, not a
            // valid "no date" state.
            if (!consumedOn) throw new Error("Date is required.");
            if (!isValidIsoDateOrEmpty(consumedOn)) throw new Error(`"${consumedOn}" isn't a valid date - use YYYY-MM-DD.`);
            const rating = Number(fd.get("rating") || 0);
            await Api.patchConsumption(log.id, {
              quantity: Number(fd.get("quantity")),
              consumed_on: consumedOn,
              note: fd.get("note")?.trim() || null,
              rating: rating > 0 ? rating : null,
            });
            close();
            toast("Updated.");
            onDone();
          } catch (err) {
            errorBox.textContent = err.message;
            errorBox.style.display = "block";
          } finally {
            submitBtn.disabled = false;
          }
        });
      },
    });
  }

  async function consumed(root, ctx) {
    if (!ctx.user) {
      location.hash = "#/login";
      return;
    }
    root.innerHTML = `<div class="page-head"><h1>Drinking history</h1></div><div id="list">${spinnerHtml()}</div>`;
    try {
      const logs = await Api.listConsumption();
      const list = root.querySelector("#list");
      if (!logs.length) {
        list.innerHTML = `<div class="panel empty-note">Nothing logged yet. Drink something and log a note!</div>`;
        return;
      }
      list.innerHTML = `<div class="feed-list">${logs
        .map(
          (log) => `<div class="feed-row" style="display:block; position:relative">
            <div style="float:right; display:flex; gap:6px;">
              <button class="btn btn-icon" data-edit="${log.id}">Edit</button>
              <button class="btn btn-icon" data-del="${log.id}">Del</button>
            </div>
            <div><strong>${escapeHtml(log.beer.name)}</strong> <span class="subtle">&mdash; ${escapeHtml(
            log.beer.brewery.name
          )}</span> <span class="meta">${fmtDate(log.consumed_on)} &middot; &times;${log.quantity}</span></div>
            ${log.rating ? `<div>${starsReadonly(log.rating)}</div>` : ""}
            ${log.note ? `<div class="subtle">${escapeHtml(log.note)}</div>` : ""}
          </div>`
        )
        .join("")}</div>`;
      list.querySelectorAll("[data-edit]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const log = logs.find((l) => l.id === Number(btn.dataset.edit));
          if (log) openEditLogModal(log, () => consumed(root, ctx));
        });
      });
      list.querySelectorAll("[data-del]").forEach((btn) => {
        btn.addEventListener("click", () => {
          confirmDelete("Delete this log entry?", async () => {
            try {
              await Api.deleteConsumption(Number(btn.dataset.del));
              toast("Deleted.");
              consumed(root, ctx);
            } catch (e) {
              toast(e.message, "error");
            }
          });
        });
      });
    } catch (e) {
      root.querySelector("#list").innerHTML = `<div class="panel empty-note">Couldn't load your history.</div>`;
    }
  }

  async function importExport(root, ctx) {
    if (!ctx.user) {
      location.hash = "#/login";
      return;
    }
    root.innerHTML = `
      <div class="page-head"><h1>Import / Export</h1></div>
      <div class="panel" style="margin-bottom:20px">
        <h3>Export</h3>
        <p>Download your entire cellar as a CSV file.</p>
        <button class="btn btn-primary" id="export-btn">Download CSV</button>
      </div>
      <div class="panel">
        <h3>Import</h3>
        <p>Upload a CSV with columns: <code>brewery, beer, style, abv, location, custom_location, quantity, size_oz, bottle_date, best_before, batch_notes, trade_status</code></p>
        <div class="csv-drop">
          <input type="file" accept=".csv" id="import-file" />
        </div>
        <div id="import-result" style="margin-top:14px"></div>
      </div>
    `;
    root.querySelector("#export-btn").addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      try {
        const { blob, filename } = await Api.exportCellar();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      } catch (err) {
        toast(err.message, "error");
      } finally {
        btn.disabled = false;
      }
    });

    root.querySelector("#import-file").addEventListener("change", async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const resultBox = root.querySelector("#import-result");
      resultBox.innerHTML = spinnerHtml();
      try {
        const result = await Api.importCellar(file);
        resultBox.innerHTML = `<div class="form-error" style="background:var(--secondary-wash);border-color:var(--secondary);color:var(--text)">
          Imported ${result.created} bottle${result.created === 1 ? "" : "s"}${
          result.skipped ? `, skipped ${result.skipped}` : ""
        }.
          ${result.errors && result.errors.length ? "<br>" + result.errors.map(escapeHtml).join("<br>") : ""}
        </div>`;
      } catch (err) {
        resultBox.innerHTML = `<div class="form-error">${escapeHtml(err.message)}</div>`;
      }
      e.target.value = "";
    });
  }

  function adminUserRowHtml(u, ctx) {
    const isSelf = ctx.account.id === u.id;
    return `
      <div class="entry-card" data-user-id="${u.id}">
        <div class="entry-main">
          <h3>${escapeHtml(u.display_name || u.username)}${isSelf ? ` <span class="subtle">(you)</span>` : ""}</h3>
          <div class="entry-meta">
            <span>${escapeHtml(u.username)}</span>
            <span class="dot">&middot;</span><span>${escapeHtml(u.email)}</span>
            <span class="dot">&middot;</span><span>${u.cellar_count} bottle${u.cellar_count === 1 ? "" : "s"}</span>
            ${u.is_admin ? `<span class="badge badge-admin">Admin</span>` : ""}
            ${u.has_oidc ? `<span class="badge badge-cellar">OIDC</span>` : ""}
          </div>
        </div>
        <div class="entry-actions">
          <div class="row">
            <button class="btn btn-icon" data-act="reset-pw" title="Reset password">Reset PW</button>
            <button class="btn btn-icon" data-act="toggle-admin" title="${u.is_admin ? "Remove admin" : "Make admin"}">${
      u.is_admin ? "&minus;Admin" : "+Admin"
    }</button>
          </div>
          <div class="row">
            <button class="btn btn-icon" data-act="delete" ${isSelf ? "disabled" : ""} title="${
      isSelf ? "Delete your own account from the Account page instead" : "Delete user"
    }">Delete</button>
          </div>
        </div>
      </div>
    `;
  }

  function wireAdminUserRows(container, users, ctx, reload) {
    container.querySelectorAll("[data-user-id]").forEach((card) => {
      const id = Number(card.dataset.userId);
      const u = users.find((x) => x.id === id);
      if (!u) return;

      card.querySelector('[data-act="reset-pw"]').addEventListener("click", () => {
        openResetPasswordModal(u, reload);
      });

      card.querySelector('[data-act="toggle-admin"]').addEventListener("click", async () => {
        try {
          await Api.adminPatchUser(u.id, { is_admin: !u.is_admin });
          toast(u.is_admin ? "Admin removed." : "Now an admin.");
          reload();
        } catch (e) {
          toast(e.message, "error");
        }
      });

      const delBtn = card.querySelector('[data-act="delete"]');
      if (!delBtn.disabled) {
        delBtn.addEventListener("click", () => {
          confirmDelete(
            `Delete ${u.username}? This removes their entire cellar, history, and account. This can't be undone.`,
            async () => {
              try {
                await Api.adminDeleteUser(u.id);
                toast("User deleted.");
                reload();
              } catch (e) {
                toast(e.message, "error");
              }
            }
          );
        });
      }
    });
  }

  function openResetPasswordModal(user, onDone) {
    const html = `
      <button class="modal-close" data-close>&times;</button>
      <h2>Reset password for ${escapeHtml(user.username)}</h2>
      <p class="subtle">Sets their password directly - they aren't notified, so you'll need to tell them the new one yourself.</p>
      <form data-reset-form>
        <div class="field">
          <label>New password</label>
          <input class="input" type="password" name="new_password" minlength="8" required autofocus />
          <div class="field-hint">At least 8 characters.</div>
        </div>
        <div class="form-error" data-error style="display:none"></div>
        <div class="form-actions">
          <button type="submit" class="btn btn-primary btn-block">Set new password</button>
        </div>
      </form>
    `;
    openModal(html, {
      onMount(modalEl, close) {
        modalEl.querySelector("[data-close]").addEventListener("click", close);
        const form = modalEl.querySelector("[data-reset-form]");
        const errorBox = modalEl.querySelector("[data-error]");
        form.addEventListener("submit", async (e) => {
          e.preventDefault();
          errorBox.style.display = "none";
          const fd = new FormData(form);
          const submitBtn = form.querySelector('button[type="submit"]');
          submitBtn.disabled = true;
          try {
            await Api.adminResetPassword(user.id, fd.get("new_password"));
            close();
            toast("Password updated.");
            onDone();
          } catch (err) {
            errorBox.textContent = err.message;
            errorBox.style.display = "block";
          } finally {
            submitBtn.disabled = false;
          }
        });
      },
    });
  }

  function openAddUserModal(onSaved, smtpEnabled) {
    const html = `
      <button class="modal-close" data-close>&times;</button>
      <h2>Add a user</h2>
      <form data-adduser-form>
        <div class="field"><label>Username</label><input class="input" name="username" pattern="[a-zA-Z0-9_\\-]{3,32}" required autofocus /></div>
        <div class="field"><label>Email</label><input class="input" type="email" name="email" required /></div>
        <div class="field">
          <label>Password</label>
          <input class="input" type="password" name="password" minlength="8" required />
          <div class="field-hint">At least 8 characters. Share it with them yourself - there's no email step.</div>
        </div>
        <label class="checkbox-row"><input type="checkbox" name="is_admin" /> Make this user an admin</label>
        ${
          smtpEnabled
            ? `<label class="checkbox-row"><input type="checkbox" name="send_welcome_email" checked /> Send them a welcome email</label>`
            : `<div class="field-hint">Outgoing email isn't configured on this instance, so no welcome email will be sent.</div>`
        }
        <div class="form-error" data-error style="display:none"></div>
        <div class="form-actions">
          <button type="submit" class="btn btn-primary btn-block">Create user</button>
        </div>
      </form>
    `;
    openModal(html, {
      onMount(modalEl, close) {
        modalEl.querySelector("[data-close]").addEventListener("click", close);
        const form = modalEl.querySelector("[data-adduser-form]");
        const errorBox = modalEl.querySelector("[data-error]");
        form.addEventListener("submit", async (e) => {
          e.preventDefault();
          errorBox.style.display = "none";
          const fd = new FormData(form);
          const submitBtn = form.querySelector('button[type="submit"]');
          submitBtn.disabled = true;
          try {
            await Api.adminCreateUser({
              username: fd.get("username"),
              email: fd.get("email"),
              password: fd.get("password"),
              is_admin: fd.get("is_admin") === "on",
              send_welcome_email: smtpEnabled && fd.get("send_welcome_email") === "on",
            });
            close();
            toast("User created.");
            onSaved();
          } catch (err) {
            errorBox.textContent = err.message;
            errorBox.style.display = "block";
          } finally {
            submitBtn.disabled = false;
          }
        });
      },
    });
  }

  async function admin(root, ctx) {
    if (!ctx.user) {
      location.hash = "#/login";
      return;
    }
    if (!ctx.account.is_admin) {
      root.innerHTML = `<div class="page-head"><h1>Admin</h1></div><div class="panel empty-note">You don't have access to this page.</div>`;
      return;
    }

    root.innerHTML = `
      <div class="page-head"><h1>Admin</h1></div>
      <div class="panel" style="margin-bottom:20px" id="settings-panel">${spinnerHtml()}</div>
      <div class="panel" style="margin-bottom:20px" id="smtp-panel">${spinnerHtml()}</div>
      <div class="page-head" style="margin-bottom:12px">
        <h2 style="font-size:19px; margin:0">Users</h2>
        <button class="btn btn-primary btn-sm" id="add-user-btn">+ Add user</button>
      </div>
      <div id="users-list" style="margin-bottom:20px">${spinnerHtml()}</div>
      <div class="panel" style="margin-bottom:20px" id="breweries-panel">${spinnerHtml()}</div>
      <div class="panel" id="backup-panel">${spinnerHtml()}</div>
    `;

    let currentSettings = null;

    async function loadSettings() {
      const panel = root.querySelector("#settings-panel");
      try {
        currentSettings = await Api.adminGetSettings();
        panel.innerHTML = `
          <h3>Instance settings</h3>
          <div class="settings-grid">
            ${toggleRow(
              "registration_enabled",
              "Allow new registrations",
              "Turn off to stop new password sign-ups while existing accounts keep working.",
              currentSettings.registration_enabled
            )}
          </div>
          <div class="field-hint" style="margin-top:10px">
            Password login: ${currentSettings.password_auth_enabled ? "enabled" : "disabled"} &middot;
            OIDC/SSO: ${currentSettings.oidc_enabled ? "enabled" : "disabled"}
            &mdash; both are set via environment variables and need a restart to change. Email is configured below.
          </div>
        `;
        panel.querySelector('[data-toggle="registration_enabled"]').addEventListener("change", async (e) => {
          const checked = e.target.checked;
          try {
            await Api.adminPatchSettings({ registration_enabled: checked });
            toast("Saved.");
          } catch (err) {
            toast(err.message, "error");
            e.target.checked = !checked;
          }
        });
      } catch (e) {
        panel.innerHTML = `<div class="empty-note">Couldn't load settings: ${escapeHtml(e.message)}</div>`;
      }
    }

    function renderSmtpPanel(s) {
      currentSettings = s;
      const panel = root.querySelector("#smtp-panel");
      panel.innerHTML = `
        <h3>Email (SMTP)</h3>
        <p class="field-hint" style="margin-top:-4px; margin-bottom:14px">
          ${
            s.smtp_enabled
              ? `Currently sending via <strong>${escapeHtml(s.smtp_effective_summary)}</strong>.`
              : `Not configured. Fill in at least a host and from-address below (or set the matching <code>CELLAR_SMTP_*</code> env vars) to enable password reset and welcome emails.`
          }
          Anything left blank here falls back to its environment variable, if one is set.
        </p>
        <form data-smtp-form>
          <div class="field-row">
            <div class="field"><label>Host</label><input class="input" name="smtp_host" value="${escapeHtml(s.smtp_host || "")}" placeholder="smtp.example.com" /></div>
            <div class="field"><label>Port</label><input class="input" type="number" name="smtp_port" value="${s.smtp_port || ""}" placeholder="587" /></div>
          </div>
          <div class="field">
            <label>Security</label>
            <select class="input" name="smtp_security" style="width:auto">
              <option value="starttls" ${(s.smtp_security || "starttls") === "starttls" ? "selected" : ""}>STARTTLS</option>
              <option value="ssl" ${s.smtp_security === "ssl" ? "selected" : ""}>Implicit SSL/TLS</option>
              <option value="none" ${s.smtp_security === "none" ? "selected" : ""}>None (trusted local relay only)</option>
            </select>
          </div>
          <div class="field-row">
            <div class="field"><label>Username <span class="subtle">(optional)</span></label><input class="input" name="smtp_username" value="${escapeHtml(s.smtp_username || "")}" autocomplete="off" /></div>
            <div class="field">
              <label>Password <span class="subtle">(optional)</span></label>
              <input class="input" type="password" name="smtp_password" placeholder="${s.smtp_password_set ? "•••••••• (unchanged)" : ""}" autocomplete="new-password" />
            </div>
          </div>
          ${
            s.smtp_password_set
              ? `<label class="checkbox-row"><input type="checkbox" name="clear_password" /> Clear the stored password</label>`
              : ""
          }
          <div class="field-row">
            <div class="field"><label>From address</label><input class="input" type="email" name="smtp_from_email" value="${escapeHtml(s.smtp_from_email || "")}" placeholder="beerkeeper@yourdomain.com" /></div>
            <div class="field"><label>From name</label><input class="input" name="smtp_from_name" value="${escapeHtml(s.smtp_from_name || "")}" placeholder="BeerKeeper" /></div>
          </div>
          <label class="checkbox-row"><input type="checkbox" name="smtp_skip_cert_verify" ${s.smtp_skip_cert_verify ? "checked" : ""} /> Skip certificate verification <span class="subtle">(only for a self-signed internal relay)</span></label>
          <div class="form-error" data-smtp-error style="display:none"></div>
          <div class="form-actions">
            <button type="submit" class="btn btn-primary">Save email settings</button>
          </div>
        </form>
        <div class="auth-divider"><span>test it</span></div>
        <form data-smtp-test-form>
          <div class="field">
            <label>Send a test email to</label>
            <input class="input" type="email" name="test_email" value="${escapeHtml(ctx.account.email || "")}" placeholder="you@example.com" required />
          </div>
          <div class="form-error" data-test-error style="display:none"></div>
          <div class="field-hint" data-test-success style="display:none; color:var(--secondary)"></div>
          <div class="form-actions">
            <button type="submit" class="btn btn-ghost">Send test email</button>
          </div>
        </form>
      `;

      const smtpForm = panel.querySelector("[data-smtp-form]");
      const smtpError = panel.querySelector("[data-smtp-error]");
      smtpForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        smtpError.style.display = "none";
        const fd = new FormData(smtpForm);
        const payload = {
          smtp_host: fd.get("smtp_host") || "",
          smtp_port: fd.get("smtp_port") ? Number(fd.get("smtp_port")) : null,
          smtp_security: fd.get("smtp_security"),
          smtp_username: fd.get("smtp_username") || "",
          smtp_from_email: fd.get("smtp_from_email") || "",
          smtp_from_name: fd.get("smtp_from_name") || "",
          smtp_skip_cert_verify: fd.get("smtp_skip_cert_verify") === "on",
        };
        if (fd.get("clear_password") === "on") {
          payload.smtp_password = "";
        } else if (fd.get("smtp_password")) {
          payload.smtp_password = fd.get("smtp_password");
        }
        const submitBtn = smtpForm.querySelector('button[type="submit"]');
        submitBtn.disabled = true;
        try {
          const updated = await Api.adminPatchSettings(payload);
          renderSmtpPanel(updated);
          toast("Email settings saved.");
        } catch (err) {
          smtpError.textContent = err.message;
          smtpError.style.display = "block";
          submitBtn.disabled = false;
        }
      });

      const testForm = panel.querySelector("[data-smtp-test-form]");
      const testError = panel.querySelector("[data-test-error]");
      const testSuccess = panel.querySelector("[data-test-success]");
      testForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        testError.style.display = "none";
        testSuccess.style.display = "none";
        const fd = new FormData(testForm);
        const submitBtn = testForm.querySelector('button[type="submit"]');
        submitBtn.disabled = true;
        try {
          await Api.adminSendTestEmail(fd.get("test_email"));
          testSuccess.textContent = `Sent to ${fd.get("test_email")}.`;
          testSuccess.style.display = "block";
        } catch (err) {
          testError.textContent = err.message;
          testError.style.display = "block";
        } finally {
          submitBtn.disabled = false;
        }
      });
    }

    async function loadSmtpPanel() {
      const panel = root.querySelector("#smtp-panel");
      try {
        const s = currentSettings || (await Api.adminGetSettings());
        renderSmtpPanel(s);
      } catch (e) {
        panel.innerHTML = `<div class="empty-note">Couldn't load email settings: ${escapeHtml(e.message)}</div>`;
      }
    }

    async function loadUsers() {
      const container = root.querySelector("#users-list");
      container.innerHTML = spinnerHtml();
      try {
        const users = await Api.adminListUsers();
        container.innerHTML = `<div class="entry-list">${users.map((u) => adminUserRowHtml(u, ctx)).join("")}</div>`;
        wireAdminUserRows(container, users, ctx, loadUsers);
      } catch (e) {
        container.innerHTML = `<div class="panel empty-note">Couldn't load users: ${escapeHtml(e.message)}</div>`;
      }
    }

    root.querySelector("#add-user-btn").addEventListener("click", () => {
      openAddUserModal(loadUsers, !!(currentSettings && currentSettings.smtp_enabled));
    });

    let breweriesSearchToken = 0;
    async function loadBreweriesPanel() {
      const panel = root.querySelector("#breweries-panel");
      panel.innerHTML = `
        <h3>Breweries</h3>
        <p class="field-hint" style="margin-top:-4px">
          The shared brewery list used for autocomplete across the whole instance - rename or clean up
          duplicates, or add ones you know you'll need. A brewery can only be deleted once nothing
          references it.
        </p>
        <div class="form-actions" style="margin-top:10px; justify-content:flex-start; gap:8px;">
          <button class="btn btn-primary btn-sm" id="add-brewery-btn">+ Add brewery</button>
          <button class="btn btn-ghost btn-sm" id="export-breweries-btn">Download CSV</button>
          <button class="btn btn-ghost btn-sm" id="import-breweries-btn">Upload CSV</button>
          <input type="file" accept=".csv" id="brewery-import-file" style="display:none" />
        </div>
        <div class="field" style="margin-top:14px">
          <input class="input" id="brewery-search" placeholder="Search breweries by name&hellip;" autocomplete="off" />
        </div>
        <div id="brewery-results" class="field-hint">Click the search box to browse breweries, or start typing to filter.</div>
      `;

      const resultsEl = panel.querySelector("#brewery-results");

      async function runSearch(q) {
        const myToken = ++breweriesSearchToken;
        resultsEl.className = "";
        resultsEl.innerHTML = spinnerHtml();
        let results;
        try {
          results = await Api.adminListBreweries(q.trim());
        } catch (err) {
          if (myToken !== breweriesSearchToken) return;
          resultsEl.innerHTML = `<div class="empty-note">Couldn't load: ${escapeHtml(err.message)}</div>`;
          return;
        }
        if (myToken !== breweriesSearchToken) return; // a newer search finished first
        if (!results.length) {
          resultsEl.innerHTML = q.trim()
            ? `<div class="empty-note">No breweries match "${escapeHtml(q)}".</div>`
            : `<div class="empty-note">No breweries yet - add the first one below.</div>`;
          return;
        }
        resultsEl.innerHTML = `<div class="entry-list">${results
          .map(
            (b) => `<div class="entry-card" style="padding:10px 14px;">
              <div class="entry-main">
                <h3 style="font-size:15px; margin-bottom:2px;">${escapeHtml(b.name)}</h3>
                <div class="entry-meta">
                  ${b.website ? `<a href="${escapeHtml(b.website)}" target="_blank" rel="noopener noreferrer">${escapeHtml(b.website)}</a>` : `<span class="subtle">No website</span>`}
                  <span>&middot;</span>
                  <span>${b.beer_count} beer${b.beer_count === 1 ? "" : "s"}</span>
                </div>
              </div>
              <div class="entry-actions">
                <div class="row">
                  <button class="btn btn-icon" data-edit-brewery="${b.id}">Edit</button>
                  <button class="btn btn-icon" data-del-brewery="${b.id}" ${b.beer_count ? "disabled title=\"In use - can't delete\"" : ""}>Del</button>
                </div>
              </div>
            </div>`
          )
          .join("")}</div>`;

        resultsEl.querySelectorAll("[data-edit-brewery]").forEach((btn) => {
          btn.addEventListener("click", () => {
            const b = results.find((r) => r.id === Number(btn.dataset.editBrewery));
            if (b) openBreweryModal(b, () => runSearch(searchInput.value));
          });
        });
        resultsEl.querySelectorAll("[data-del-brewery]:not([disabled])").forEach((btn) => {
          btn.addEventListener("click", () => {
            const b = results.find((r) => r.id === Number(btn.dataset.delBrewery));
            confirmDelete(`Delete "${b.name}" from the brewery list? This can't be undone.`, async () => {
              try {
                await Api.adminDeleteBrewery(b.id);
                toast("Brewery deleted.");
                runSearch(searchInput.value);
              } catch (err) {
                toast(err.message, "error");
              }
            });
          });
        });
      }

      const searchInput = panel.querySelector("#brewery-search");
      const debouncedSearch = debounce((q) => runSearch(q), 300);
      searchInput.addEventListener("input", () => debouncedSearch(searchInput.value));
      let hasLoadedOnce = false;
      searchInput.addEventListener("focus", () => {
        if (!hasLoadedOnce) {
          hasLoadedOnce = true;
          runSearch(searchInput.value);
        }
      });

      panel.querySelector("#add-brewery-btn").addEventListener("click", () => {
        openBreweryModal(null, () => runSearch(searchInput.value));
      });

      panel.querySelector("#export-breweries-btn").addEventListener("click", async (e) => {
        const btn = e.currentTarget;
        btn.disabled = true;
        try {
          const { blob, filename } = await Api.adminExportBreweries();
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = filename;
          document.body.appendChild(a);
          a.click();
          a.remove();
          URL.revokeObjectURL(url);
        } catch (err) {
          toast(err.message, "error");
        } finally {
          btn.disabled = false;
        }
      });

      const importFileInput = panel.querySelector("#brewery-import-file");
      panel.querySelector("#import-breweries-btn").addEventListener("click", () => importFileInput.click());
      importFileInput.addEventListener("change", async () => {
        const file = importFileInput.files[0];
        if (!file) return;
        try {
          const result = await Api.adminImportBreweries(file);
          toast(`Imported: ${result.created} added, ${result.skipped} skipped.`);
          if (result.errors.length) {
            toast(result.errors[0], "error");
          }
          if (searchInput.value.trim()) runSearch(searchInput.value);
        } catch (err) {
          toast(err.message, "error");
        } finally {
          importFileInput.value = "";
        }
      });
    }

    async function loadBackupPanel() {
      const panel = root.querySelector("#backup-panel");
      let status;
      try {
        status = await Api.adminGetRestoreStatus();
      } catch (e) {
        status = { pending: false };
      }
      panel.innerHTML = `
        <h3>Backup and restore</h3>
        <p class="field-hint" style="margin-top:-4px">
          A single zip file with everything - every account, cellar, brewery, and beer, plus your
          custom beer styles list - not just your own data, for moving to a new install or keeping
          an off-site copy.
        </p>
        ${
          status.pending
            ? `<div class="form-error" style="background:var(--danger-wash); border-color:var(--danger); color:var(--danger); display:flex; align-items:center; justify-content:space-between; gap:12px;">
                 <span>A restore is staged and will replace this entire instance on next restart.</span>
                 <button class="btn btn-icon" id="cancel-restore-btn">Cancel</button>
               </div>`
            : ""
        }
        <div class="form-actions" style="margin-top:14px">
          <button class="btn btn-primary" id="download-backup-btn">Download full backup</button>
        </div>
        <div style="margin-top:20px; padding-top:16px; border-top:1px solid var(--border)">
          <h4 style="margin:0 0 6px">Restore from backup</h4>
          <p class="field-hint" style="margin-top:0">
            <strong>Replaces everything on this instance</strong> - every user, bottle, setting, and
            style - with what's in the file. Takes effect on the next restart, not immediately, so
            there's a chance to cancel first.
          </p>
          <input type="file" accept=".zip" id="restore-file" />
          <div class="form-error" data-restore-error style="display:none; margin-top:10px"></div>
          <div class="form-actions" style="margin-top:10px">
            <button class="btn btn-ghost" id="upload-restore-btn">Upload and stage restore</button>
          </div>
        </div>
      `;

      panel.querySelector("#download-backup-btn").addEventListener("click", async (e) => {
        const btn = e.currentTarget;
        btn.disabled = true;
        try {
          const { blob, filename } = await Api.adminDownloadBackup();
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = filename;
          document.body.appendChild(a);
          a.click();
          a.remove();
          URL.revokeObjectURL(url);
        } catch (err) {
          toast(err.message, "error");
        } finally {
          btn.disabled = false;
        }
      });

      const cancelBtn = panel.querySelector("#cancel-restore-btn");
      if (cancelBtn) {
        cancelBtn.addEventListener("click", async () => {
          try {
            await Api.adminCancelRestore();
            toast("Staged restore cancelled.");
            loadBackupPanel();
          } catch (err) {
            toast(err.message, "error");
          }
        });
      }

      panel.querySelector("#upload-restore-btn").addEventListener("click", () => {
        const fileInput = panel.querySelector("#restore-file");
        const file = fileInput.files[0];
        const errorBox = panel.querySelector("[data-restore-error]");
        errorBox.style.display = "none";
        if (!file) {
          errorBox.textContent = "Choose a backup file first.";
          errorBox.style.display = "block";
          return;
        }
        confirmDelete(
          "This will replace every account, bottle, setting, and style on this instance with what's in the uploaded file, the next time it restarts. This can't be undone. Continue?",
          async () => {
            try {
              await Api.adminUploadRestore(file);
              toast("Restore staged - restart the app to apply it.");
              fileInput.value = "";
              loadBackupPanel();
            } catch (err) {
              errorBox.textContent = err.message;
              errorBox.style.display = "block";
            }
          }
        );
      });
    }

    await loadSettings();
    loadSmtpPanel();
    loadUsers();
    loadBreweriesPanel();
    loadBackupPanel();
  }

  return {
    home,
    login,
    register,
    forgotPassword,
    resetPassword,
    cellar,
    account,
    admin,
    browse,
    publicCellar,
    publicTrades,
    consumed,
    importExport,
  };
})();

