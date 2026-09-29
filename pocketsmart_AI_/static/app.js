// ============================================================
// PocketSmart Frontend JavaScript
// ============================================================

async function parseResponse(response) {
    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
        throw new Error(
            data.detail || "Something went wrong."
        );
    }

    return data;
}


// ============================================================
// AUTHENTICATION FORMS
// ============================================================

function bindAuthForm(
    formId,
    url,
    successUrl
) {
    const form = document.getElementById(formId);

    if (!form) {
        return;
    }

    form.addEventListener(
        "submit",
        async function (event) {

            event.preventDefault();

            const message =
                document.getElementById(
                    "formMessage"
                );

            message.textContent =
                "Please wait...";

            message.className =
                "message";

            const body =
                Object.fromEntries(
                    new FormData(form).entries()
                );

            try {

                const response =
                    await fetch(
                        url,
                        {
                            method: "POST",
                            headers: {
                                "Content-Type":
                                    "application/json"
                            },
                            body:
                                JSON.stringify(body)
                        }
                    );

                await parseResponse(response);

                window.location.href =
                    successUrl;

            } catch (error) {

                message.textContent =
                    error.message;

                message.className =
                    "message error";
            }
        }
    );
}


// ============================================================
// MONEY FORMATTER
// ============================================================

function money(value) {

    return new Intl.NumberFormat(
        "en-IN",
        {
            style: "currency",
            currency: "INR",
            maximumFractionDigits: 0
        }
    ).format(
        Number(value || 0)
    );
}


// ============================================================
// HTML ESCAPING
// ============================================================

function escapeHtml(value) {

    return String(
        value ?? ""
    ).replace(
        /[&<>'"]/g,
        function (character) {

            return {
                "&": "&amp;",
                "<": "&lt;",
                ">": "&gt;",
                "'": "&#39;",
                '"': "&quot;"
            }[character];

        }
    );
}


// ============================================================
// RESULT RENDERING
// ============================================================

function renderResult(data) {

    const categories =
        (data.budget_breakdown || [])
            .map(
                category => {

                    const items =
                        (category.items || [])
                            .map(
                                item => {

                                    const links =
                                        Object.entries(
                                            item.shopping_links || {}
                                        )
                                        .map(
                                            ([name, url]) =>
                                                `
                                                <a
                                                    target="_blank"
                                                    rel="noopener"
                                                    href="${escapeHtml(url)}"
                                                >
                                                    ${escapeHtml(name)}
                                                </a>
                                                `
                                        )
                                        .join("");

                                    return `
                                        <div class="item">

                                            <div>

                                                <strong>
                                                    ${escapeHtml(
                                                        item.name ||
                                                        "Recommended item"
                                                    )}
                                                </strong>

                                                <p>
                                                    ${escapeHtml(
                                                        item.description ||
                                                        ""
                                                    )}
                                                </p>

                                                <span>
                                                    ${money(
                                                        item.estimated_price
                                                    )}
                                                </span>

                                            </div>

                                            <div class="links">
                                                ${links}
                                            </div>

                                        </div>
                                    `;
                                }
                            )
                            .join("");

                    return `
                        <div class="recommendation-card">

                            <div class="rec-head">

                                <h3>
                                    ${escapeHtml(
                                        category.category
                                    )}
                                </h3>

                                <strong>
                                    ${money(
                                        category.total_cost
                                    )}
                                </strong>

                            </div>

                            ${items}

                        </div>
                    `;
                }
            )
            .join("");


    const suggestions =
        (data.additional_suggestions || [])
            .map(
                suggestion =>
                    `
                    <li>
                        ${escapeHtml(suggestion)}
                    </li>
                    `
            )
            .join("");


    let outfitAnalysis = "";

    if (data.outfit_analysis) {

        const colors =
            (data.outfit_analysis.colors || [])
                .map(
                    color =>
                        `<li>${escapeHtml(color)}</li>`
                )
                .join("");

        outfitAnalysis = `
            <div class="suggestions">

                <h3>
                    Outfit Analysis
                </h3>

                <p>
                    <strong>Style:</strong>
                    ${escapeHtml(
                        data.outfit_analysis.style || "Not available"
                    )}
                </p>

                <p>
                    <strong>Formality:</strong>
                    ${escapeHtml(
                        data.outfit_analysis.formality || "Not available"
                    )}
                </p>

                ${
                    colors
                        ? `
                            <p>
                                <strong>Visible Colors:</strong>
                            </p>
                            <ul>
                                ${colors}
                            </ul>
                        `
                        : ""
                }

            </div>
        `;
    }


    return `
        <div class="result-wrap">

            <div class="result-summary">

                <div>
                    <span>
                        Total Budget
                    </span>

                    <strong>
                        ${money(
                            data.total_budget
                        )}
                    </strong>
                </div>

                <div>
                    <span>
                        Remaining
                    </span>

                    <strong>
                        ${money(
                            data.remaining_budget
                        )}
                    </strong>
                </div>

            </div>

            ${outfitAnalysis}

            <h2>
                Recommended Budget Breakdown
            </h2>

            ${categories}

            <div class="suggestions">

                <h3>
                    Additional Suggestions
                </h3>

                <ul>
                    ${suggestions}
                </ul>

            </div>

        </div>
    `;
}


// ============================================================
// PLANNER FORMS
// ============================================================

function bindPlanner(
    formId,
    url,
    mode
) {

    const form =
        document.getElementById(formId);

    const result =
        document.getElementById("result");

    if (!form || !result) {
        return;
    }


    form.addEventListener(
        "submit",
        async function (event) {

            event.preventDefault();

            result.innerHTML = `
                <div class="loading">
                    Generating your recommendation...
                </div>
            `;

            try {

                const options = {
                    method: "POST"
                };


                // Jewelry form
                if (mode === "form") {

                    options.body =
                        new FormData(form);

                }


                // Home and party JSON forms
                else {

                    options.headers = {
                        "Content-Type":
                            "application/json"
                    };

                    const raw =
                        Object.fromEntries(
                            new FormData(form).entries()
                        );


                    if (
                        raw.total_budget !== undefined
                    ) {

                        raw.total_budget =
                            Number(
                                raw.total_budget
                            );
                    }


                    if (
                        raw.num_lights !== undefined
                    ) {

                        raw.num_lights =
                            Number(
                                raw.num_lights || 0
                            );
                    }


                    if (
                        raw.num_fans !== undefined
                    ) {

                        raw.num_fans =
                            Number(
                                raw.num_fans || 0
                            );
                    }


                    if (
                        raw.num_furniture !== undefined
                    ) {

                        raw.num_furniture =
                            Number(
                                raw.num_furniture || 0
                            );
                    }


                    if (
                        raw.num_dining_tables !== undefined
                    ) {

                        raw.num_dining_tables =
                            Number(
                                raw.num_dining_tables || 0
                            );
                    }


                    if (
                        raw.num_guests !== undefined
                    ) {

                        raw.num_guests =
                            Number(
                                raw.num_guests || 0
                            );
                    }


                    if (raw.rooms) {

                        raw.rooms =
                            raw.rooms
                                .split(",")
                                .map(
                                    value =>
                                        value.trim()
                                )
                                .filter(
                                    Boolean
                                );

                    } else {

                        raw.rooms = [];

                    }


                    options.body =
                        JSON.stringify(raw);
                }


                const response =
                    await fetch(
                        url,
                        options
                    );


                const data =
                    await parseResponse(
                        response
                    );


                result.innerHTML =
                    renderResult(data);


                result.scrollIntoView({
                    behavior: "smooth",
                    block: "start"
                });


            } catch (error) {

                result.innerHTML = `
                    <div class="message error">
                        ${escapeHtml(
                            error.message
                        )}
                    </div>
                `;
            }
        }
    );
}