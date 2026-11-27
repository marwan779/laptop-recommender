using System.Globalization;
using System.Net;
using System.Text;
using Users.Application.Common.Interfaces.Jobs;

namespace Users.Application.Features.Notifications.Email;

/// <summary>
/// Builds responsive, inline-CSS HTML/CSS email templates compatible with Gmail,
/// Apple Mail, and Outlook for price and stock alerts.
/// </summary>
public static class EmailBodyBuilder
{
    public static string BuildPriceAlertSubject(PriceAlertEmailJobPayload payload)
    {
        var isArabic = IsArabic(payload.PreferredLanguage);
        var title = string.IsNullOrWhiteSpace(payload.LaptopTitle)
            ? payload.CanonicalId
            : payload.LaptopTitle.Trim();

        return (payload.ChangeType.ToUpperInvariant(), isArabic) switch
        {
            ("PRICE_DROP", true) => $"انخفاض سعر: {title}",
            ("PRICE_DROP", false) => $"Price Drop: {title}",
            ("RESTOCK" or "BACK_IN_STOCK", true) => $"متوفر الآن: {title}",
            ("RESTOCK" or "BACK_IN_STOCK", false) => $"Back in Stock: {title}",
            ("OUT_OF_STOCK", true) => $"نفد المخزون: {title}",
            ("OUT_OF_STOCK", false) => $"Out of Stock: {title}",
            (_, true) => $"تحديث سعر: {title}",
            _ => $"Price Update: {title}",
        };
    }

    public static string BuildPriceAlertPlainText(PriceAlertEmailJobPayload payload)
    {
        var title = string.IsNullOrWhiteSpace(payload.LaptopTitle)
            ? payload.CanonicalId
            : payload.LaptopTitle.Trim();
        var store = string.IsNullOrWhiteSpace(payload.CheapestStore) ? "—" : payload.CheapestStore.Trim();
        var oldPrice = payload.OldPriceEgp.HasValue ? FormatEgp(payload.OldPriceEgp.Value) : "—";
        var newPrice = payload.NewPriceEgp.HasValue ? FormatEgp(payload.NewPriceEgp.Value) : "—";

        var sb = new StringBuilder();
        sb.AppendLine($"Hi {payload.FullName},");
        sb.AppendLine();
        sb.AppendLine($"{title} ({payload.ChangeType})");
        sb.AppendLine($"Previous Price: {oldPrice}");
        sb.AppendLine($"Current Price:  {newPrice}");
        sb.AppendLine($"Store:          {store}");
        sb.AppendLine($"In Stock:       {(payload.InStock ? "Yes" : "No")}");
        return sb.ToString();
    }

    public static string BuildPriceAlertHtml(PriceAlertEmailJobPayload payload)
    {
        var isArabic = IsArabic(payload.PreferredLanguage);
        var dir = isArabic ? "rtl" : "ltr";
        var align = isArabic ? "right" : "left";

        var safeName = WebUtility.HtmlEncode(string.IsNullOrWhiteSpace(payload.FullName) ? "there" : payload.FullName.Trim());
        var safeTitle = WebUtility.HtmlEncode(string.IsNullOrWhiteSpace(payload.LaptopTitle) ? payload.CanonicalId : payload.LaptopTitle.Trim());
        var safeCanonicalId = WebUtility.HtmlEncode(payload.CanonicalId);
        var safeStore = WebUtility.HtmlEncode(string.IsNullOrWhiteSpace(payload.CheapestStore) ? "Egyptian Storefront" : payload.CheapestStore.Trim());

        var normalizedType = (payload.ChangeType ?? "PRICE_CHANGE").Trim().ToUpperInvariant();
        var (badgeText, badgeColor, badgeBg, badgeBorder) = normalizedType switch
        {
            "PRICE_DROP" => (isArabic ? "انخفاض السعر" : "PRICE DROP", "#34D399", "#0D2B24", "#1F5E4B"),
            "RESTOCK" or "BACK_IN_STOCK" => (isArabic ? "متوفر مجدداً" : "BACK IN STOCK", "#22D3EE", "#0C2730", "#1C596B"),
            "OUT_OF_STOCK" => (isArabic ? "نفد المخزون" : "OUT OF STOCK", "#F87171", "#2D1519", "#692831"),
            _ => (isArabic ? "تحديث السعر" : "PRICE UPDATE", "#F5C95C", "#2A2110", "#664E1D"),
        };

        var greeting = isArabic ? $"مرحباً {safeName}،" : $"Hi {safeName},";
        var headline = normalizedType switch
        {
            "PRICE_DROP" => isArabic ? "انخفض سعر لابتوب تتابعه في المفضلة" : "A laptop on your watchlist dropped in price",
            "RESTOCK" or "BACK_IN_STOCK" => isArabic ? "عاد اللابتوب للتوفر في المتاجر" : "Your watched laptop is back in stock",
            "OUT_OF_STOCK" => isArabic ? "تغيرت حالة توفر اللابتوب" : "Stock status changed on your watchlist",
            _ => isArabic ? "تحديث جديد لسعر اللابتوب" : "New price update for your watched laptop",
        };

        var oldPriceLabel = isArabic ? "السعر السابق" : "PREVIOUS";
        var newPriceLabel = isArabic ? "أفضل سعر الآن" : "CURRENT BEST PRICE";
        var storeLabel = isArabic ? "أرخص متجر" : "CHEAPEST STORE";
        var stockLabel = isArabic ? "حالة التوفر" : "AVAILABILITY";
        var stockValue = payload.InStock
            ? (isArabic ? "متوفر للشراء" : "In Stock")
            : (isArabic ? "غير متوفر" : "Out of Stock");
        var stockColor = payload.InStock ? "#34D399" : "#F87171";
        var ctaLabel = isArabic ? "عرض اللابتوب ومقارنة المتاجر" : "View Laptop & Store Offers";
        var preheader = isArabic
            ? $"{safeTitle} — {newPriceTextSafe(payload)} ({safeStore})"
            : $"{safeTitle} — {newPriceTextSafe(payload)} at {safeStore}";

        var oldPriceText = payload.OldPriceEgp.HasValue ? FormatEgp(payload.OldPriceEgp.Value) : "—";
        var newPriceText = payload.NewPriceEgp.HasValue ? FormatEgp(payload.NewPriceEgp.Value) : "—";

        var savingsRowHtml = string.Empty;
        if (payload.OldPriceEgp.HasValue && payload.NewPriceEgp.HasValue && payload.OldPriceEgp.Value > payload.NewPriceEgp.Value)
        {
            var diff = payload.OldPriceEgp.Value - payload.NewPriceEgp.Value;
            var pct = payload.OldPriceEgp.Value > 0 ? Math.Round((diff / payload.OldPriceEgp.Value) * 100m, 1) : 0m;
            var saveText = isArabic
                ? $"وفر {FormatEgp(diff)} ({pct}%-)"
                : $"SAVE {FormatEgp(diff)} (-{pct}%)";
            savingsRowHtml = $"""
                <tr>
                  <td style="padding-top:10px;text-align:{align};">
                    <span style="display:inline-block;background-color:#0D2B24;border:1px solid #1F5E4B;border-radius:999px;padding:5px 12px;font-size:12px;font-weight:700;color:#34D399;letter-spacing:0.4px;">
                      {WebUtility.HtmlEncode(saveText)}
                    </span>
                  </td>
                </tr>
                """;
        }

        var oldPriceBlock = payload.OldPriceEgp.HasValue && payload.OldPriceEgp != payload.NewPriceEgp
            ? $"""
              <td width="45%" valign="top" style="padding:12px 0;text-align:{align};">
                <div style="font-size:10px;font-weight:700;letter-spacing:0.9px;color:#7D8FA3;text-transform:uppercase;">{oldPriceLabel}</div>
                <div style="margin-top:6px;font-size:17px;font-weight:600;color:#7D8FA3;text-decoration:line-through;">{oldPriceText}</div>
              </td>
              """
            : string.Empty;

        var footerText = isArabic
            ? "تصلك هذه الرسالة لأنك فعّلت تنبيهات الأسعار لهذا الجهاز في Egypt Laptop Recommender."
            : "You received this alert because price & stock notifications are enabled in your Egypt Laptop Recommender watchlist.";

        var ctaUrl = $"http://localhost/?laptop={Uri.EscapeDataString(payload.CanonicalId)}";

        return $$"""
        <!DOCTYPE html>
        <html lang="{{(isArabic ? "ar" : "en")}}" dir="{{dir}}">
        <head>
          <meta charset="utf-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1.0" />
          <title>{{WebUtility.HtmlEncode(BuildPriceAlertSubject(payload))}}</title>
        </head>
        <body style="margin:0;padding:0;background-color:#080B10;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#E6EDF3;">
          <div style="display:none;max-height:0;overflow:hidden;opacity:0;">{{preheader}}</div>
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#080B10;padding:36px 14px;">
            <tr>
              <td align="center">
                <table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0" style="max-width:600px;width:100%;background-color:#10161F;border:1px solid #222E3F;border-radius:16px;overflow:hidden;">
                  <!-- Top Gold Accent Bar -->
                  <tr>
                    <td height="4" style="background-color:#E9B949;font-size:0;line-height:0;">&nbsp;</td>
                  </tr>

                  <!-- Header -->
                  <tr>
                    <td style="padding:22px 28px;background-color:#141C27;border-bottom:1px solid #1E2836;">
                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                        <tr>
                          <td style="text-align:{{align}};">
                            <div style="font-size:11px;font-weight:800;letter-spacing:1.4px;text-transform:uppercase;color:#22D3EE;">
                              EGYPT LAPTOP RECOMMENDER
                            </div>
                          </td>
                          <td align="{{(isArabic ? "left" : "right")}}">
                            <span style="display:inline-block;background-color:{{badgeBg}};border:1px solid {{badgeBorder}};border-radius:6px;padding:4px 10px;font-size:10px;font-weight:800;letter-spacing:0.9px;color:{{badgeColor}};">
                              {{badgeText}}
                            </span>
                          </td>
                        </tr>
                      </table>
                    </td>
                  </tr>

                  <!-- Greeting & Headline -->
                  <tr>
                    <td style="padding:28px 28px 18px 28px;text-align:{{align}};">
                      <div style="font-size:14px;color:#9FB0C3;margin-bottom:6px;">{{greeting}}</div>
                      <h1 style="margin:0;font-size:21px;line-height:1.35;font-weight:700;color:#F8FAFC;">
                        {{headline}}
                      </h1>
                    </td>
                  </tr>

                  <!-- Laptop Card -->
                  <tr>
                    <td style="padding:0 28px 24px 28px;">
                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#161F2B;border:1px solid #2A384C;border-radius:12px;">
                        <tr>
                          <td style="padding:22px;text-align:{{align}};">
                            <div style="font-size:18px;font-weight:700;line-height:1.4;color:#FFFFFF;">
                              {{safeTitle}}
                            </div>
                            <div style="margin-top:4px;font-family:'Courier New',Courier,monospace;font-size:11px;color:#6E8299;">
                              {{safeCanonicalId}}
                            </div>

                            <!-- Price Strip -->
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-top:18px;border-top:1px solid #233042;border-bottom:1px solid #233042;">
                              <tr>
                                <td width="55%" valign="top" style="padding:14px 0;text-align:{{align}};">
                                  <div style="font-size:10px;font-weight:700;letter-spacing:0.9px;color:#7D8FA3;text-transform:uppercase;">{{newPriceLabel}}</div>
                                  <div style="margin-top:4px;font-size:28px;font-weight:800;line-height:1.15;color:#E9B949;">{{newPriceText}}</div>
                                </td>
                                {{oldPriceBlock}}
                              </tr>
                              {{savingsRowHtml}}
                            </table>

                            <!-- Store & Availability -->
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-top:14px;">
                              <tr>
                                <td width="55%" valign="top" style="padding-top:4px;text-align:{{align}};">
                                  <div style="font-size:10px;font-weight:700;letter-spacing:0.9px;color:#7D8FA3;text-transform:uppercase;">{{storeLabel}}</div>
                                  <div style="margin-top:5px;font-size:14px;font-weight:600;color:#F1F5F9;">{{safeStore}}</div>
                                </td>
                                <td width="45%" valign="top" style="padding-top:4px;text-align:{{align}};">
                                  <div style="font-size:10px;font-weight:700;letter-spacing:0.9px;color:#7D8FA3;text-transform:uppercase;">{{stockLabel}}</div>
                                  <div style="margin-top:5px;font-size:14px;font-weight:700;color:{{stockColor}};">&#9679; {{stockValue}}</div>
                                </td>
                              </tr>
                            </table>
                          </td>
                        </tr>
                      </table>
                    </td>
                  </tr>

                  <!-- Footer -->
                  <tr>
                    <td style="padding:18px 28px;background-color:#0C1118;border-top:1px solid #1E2836;text-align:{{align}};">
                      <div style="font-size:11.5px;line-height:1.6;color:#6E8299;">
                        {{footerText}}
                      </div>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
          </table>
        </body>
        </html>
        """;
    }

    private static string newPriceTextSafe(PriceAlertEmailJobPayload payload)
        => payload.NewPriceEgp.HasValue ? FormatEgp(payload.NewPriceEgp.Value) : "—";

    public static string BuildFeedbackAdminAlertSubject(FeedbackAdminAlertEmailPayload payload)
        => $"[New Report · {payload.Category}] {payload.Title}";

    public static string BuildFeedbackAdminAlertHtml(FeedbackAdminAlertEmailPayload payload)
    {
        var safeAdmin = WebUtility.HtmlEncode(string.IsNullOrWhiteSpace(payload.AdminName) ? "Admin" : payload.AdminName.Trim());
        var safeTitle = WebUtility.HtmlEncode(payload.Title);
        var safeCategory = WebUtility.HtmlEncode(payload.Category);
        var safeReporter = WebUtility.HtmlEncode(string.IsNullOrWhiteSpace(payload.ReporterEmail) ? "Anonymous guest" : payload.ReporterEmail.Trim());
        var safeDesc = WebUtility.HtmlEncode(payload.Description);
        var laptopLine = string.IsNullOrWhiteSpace(payload.LaptopTitleSnapshot)
            ? string.Empty
            : $"""<div style="margin-top:8px;font-size:12px;color:#22D3EE;font-weight:600;">Laptop: {WebUtility.HtmlEncode(payload.LaptopTitleSnapshot)}</div>""";

        return $$"""
        <!DOCTYPE html>
        <html lang="en" dir="ltr">
        <head><meta charset="utf-8" /><title>{{WebUtility.HtmlEncode(BuildFeedbackAdminAlertSubject(payload))}}</title></head>
        <body style="margin:0;padding:0;background-color:#080B10;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#E6EDF3;">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#080B10;padding:32px 14px;">
            <tr><td align="center">
              <table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0" style="max-width:600px;width:100%;background-color:#10161F;border:1px solid #222E3F;border-radius:16px;overflow:hidden;">
                <tr><td height="4" style="background-color:#22D3EE;font-size:0;line-height:0;">&nbsp;</td></tr>
                <tr><td style="padding:20px 26px;background-color:#141C27;border-bottom:1px solid #1E2836;">
                  <div style="font-size:11px;font-weight:800;letter-spacing:1.3px;color:#22D3EE;text-transform:uppercase;">ADMIN ALERT · NEW FEEDBACK REPORT</div>
                </td></tr>
                <tr><td style="padding:24px 26px;">
                  <div style="font-size:14px;color:#9FB0C3;margin-bottom:8px;">Hi {{safeAdmin}},</div>
                  <h1 style="margin:0 0 16px 0;font-size:19px;color:#F8FAFC;">A new issue report was submitted</h1>
                  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#161F2B;border:1px solid #2A384C;border-radius:12px;">
                    <tr><td style="padding:20px;">
                      <span style="display:inline-block;background-color:#2A2110;border:1px solid #664E1D;border-radius:6px;padding:3px 9px;font-size:11px;font-weight:700;color:#F5C95C;">{{safeCategory}}</span>
                      <div style="margin-top:10px;font-size:17px;font-weight:700;color:#FFFFFF;">{{safeTitle}}</div>
                      {{laptopLine}}
                      <div style="margin-top:12px;font-size:13.5px;line-height:1.6;color:#CBD5E1;">{{safeDesc}}</div>
                      <div style="margin-top:14px;padding-top:12px;border-top:1px solid #233042;font-size:12px;color:#7D8FA3;">
                        Reporter: <strong style="color:#E6EDF3;">{{safeReporter}}</strong>
                      </div>
                    </td></tr>
                  </table>
                </td></tr>
                <tr><td align="center" style="padding:0 26px 26px 26px;">
                  <a href="http://localhost/" target="_blank" style="display:inline-block;background-color:#E9B949;color:#0A0E13;font-size:13.5px;font-weight:800;text-decoration:none;padding:12px 24px;border-radius:10px;">Open Admin Console</a>
                </td></tr>
              </table>
            </td></tr>
          </table>
        </body>
        </html>
        """;
    }

    public static string BuildFeedbackReviewedSubject(FeedbackReviewedEmailPayload payload)
    {
        var isArabic = IsArabic(payload.PreferredLanguage);
        return isArabic
            ? $"تحديث بلاغك ({payload.Status}): {payload.Title}"
            : $"Report Update ({payload.Status}): {payload.Title}";
    }

    public static string BuildFeedbackReviewedHtml(FeedbackReviewedEmailPayload payload)
    {
        var isArabic = IsArabic(payload.PreferredLanguage);
        var dir = isArabic ? "rtl" : "ltr";
        var align = isArabic ? "right" : "left";
        var safeName = WebUtility.HtmlEncode(string.IsNullOrWhiteSpace(payload.RecipientName) ? "there" : payload.RecipientName.Trim());
        var safeTitle = WebUtility.HtmlEncode(payload.Title);
        var safeStatus = WebUtility.HtmlEncode(payload.Status);
        var (badgeColor, badgeBg, badgeBorder) = payload.Status.ToUpperInvariant() switch
        {
            "RESOLVED" => ("#34D399", "#0D2B24", "#1F5E4B"),
            "IN_REVIEW" => ("#22D3EE", "#0C2730", "#1C596B"),
            "DISMISSED" => ("#9FB0C3", "#1A222D", "#334155"),
            _ => ("#F5C95C", "#2A2110", "#664E1D"),
        };

        var greeting = isArabic ? $"مرحباً {safeName}،" : $"Hi {safeName},";
        var headline = isArabic ? "تمت مراجعة بلاغك من قبل الإدارة" : "Your feedback report has been reviewed";
        var notesBlock = string.IsNullOrWhiteSpace(payload.AdminNotes)
            ? string.Empty
            : $"""
              <div style="margin-top:14px;padding:12px 14px;background-color:#10161F;border:1px solid #2A384C;border-radius:8px;font-size:13px;color:#E6EDF3;text-align:{align};">
                <strong style="color:#E9B949;">{(isArabic ? "ملاحظة الإدارة: " : "Admin note: ")}</strong>{WebUtility.HtmlEncode(payload.AdminNotes)}
              </div>
              """;

        return $$"""
        <!DOCTYPE html>
        <html lang="{{(isArabic ? "ar" : "en")}}" dir="{{dir}}">
        <head><meta charset="utf-8" /><title>{{WebUtility.HtmlEncode(BuildFeedbackReviewedSubject(payload))}}</title></head>
        <body style="margin:0;padding:0;background-color:#080B10;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#E6EDF3;">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#080B10;padding:32px 14px;">
            <tr><td align="center">
              <table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0" style="max-width:600px;width:100%;background-color:#10161F;border:1px solid #222E3F;border-radius:16px;overflow:hidden;">
                <tr><td height="4" style="background-color:#E9B949;font-size:0;line-height:0;">&nbsp;</td></tr>
                <tr><td style="padding:20px 26px;background-color:#141C27;border-bottom:1px solid #1E2836;text-align:{{align}};">
                  <span style="font-size:11px;font-weight:800;letter-spacing:1.2px;color:#22D3EE;text-transform:uppercase;">EGYPT LAPTOP RECOMMENDER</span>
                </td></tr>
                <tr><td style="padding:24px 26px;text-align:{{align}};">
                  <div style="font-size:14px;color:#9FB0C3;margin-bottom:6px;">{{greeting}}</div>
                  <h1 style="margin:0 0 16px 0;font-size:20px;color:#F8FAFC;">{{headline}}</h1>
                  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#161F2B;border:1px solid #2A384C;border-radius:12px;">
                    <tr><td style="padding:20px;text-align:{{align}};">
                      <span style="display:inline-block;background-color:{{badgeBg}};border:1px solid {{badgeBorder}};border-radius:6px;padding:4px 10px;font-size:11px;font-weight:800;color:{{badgeColor}};">{{safeStatus}}</span>
                      <div style="margin-top:10px;font-size:17px;font-weight:700;color:#FFFFFF;">{{safeTitle}}</div>
                      {{notesBlock}}
                    </td></tr>
                  </table>
                </td></tr>
              </table>
            </td></tr>
          </table>
        </body>
        </html>
        """;
    }

    private static bool IsArabic(string? preferredLanguage)
        => string.Equals(preferredLanguage?.Trim(), "ar", StringComparison.OrdinalIgnoreCase);

    private static string FormatEgp(decimal amount)
        => string.Format(CultureInfo.InvariantCulture, "{0:N0} EGP", amount);
}
