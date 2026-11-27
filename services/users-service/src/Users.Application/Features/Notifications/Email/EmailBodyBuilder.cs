using System.Globalization;
using System.Net;
using System.Text;
using Users.Application.Common.Interfaces.Jobs;

namespace Users.Application.Features.Notifications.Email;

/// <summary>
/// Builds responsive, inline-CSS HTML/CSS email templates for price and stock alerts.
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
            ("PRICE_DROP", false) => $"Price Drop Alert: {title}",
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
        var (badgeText, badgeColor, badgeBg) = normalizedType switch
        {
            "PRICE_DROP" => (isArabic ? "انخفاض السعر" : "PRICE DROP", "#34D399", "rgba(52, 211, 153, 0.14)"),
            "RESTOCK" or "BACK_IN_STOCK" => (isArabic ? "متوفر مجدداً" : "BACK IN STOCK", "#22D3EE", "rgba(34, 211, 238, 0.14)"),
            "OUT_OF_STOCK" => (isArabic ? "نفد المخزون" : "OUT OF STOCK", "#F87171", "rgba(248, 113, 113, 0.14)"),
            _ => (isArabic ? "تحديث السعر" : "PRICE UPDATE", "#E9B949", "rgba(233, 185, 73, 0.14)"),
        };

        var greeting = isArabic ? $"مرحباً {safeName}،" : $"Hi {safeName},";
        var headline = normalizedType switch
        {
            "PRICE_DROP" => isArabic ? "انخفض سعر لابتوب في قائمة المفضلة لديك" : "A laptop on your watchlist just dropped in price",
            "RESTOCK" or "BACK_IN_STOCK" => isArabic ? "عاد اللابتوب للتوفر في المتاجر" : "A laptop on your watchlist is back in stock",
            "OUT_OF_STOCK" => isArabic ? "تغيرت حالة توفر اللابتوب" : "Stock status changed for a laptop on your watchlist",
            _ => isArabic ? "تم رصد تحديث جديد للسعر" : "New price update for a laptop on your watchlist",
        };

        var oldPriceLabel = isArabic ? "السعر السابق" : "Previous Price";
        var newPriceLabel = isArabic ? "السعر الحالي" : "Current Best Price";
        var storeLabel = isArabic ? "أرخص متجر" : "Cheapest Store";
        var stockLabel = isArabic ? "التوفر" : "Availability";
        var stockValue = payload.InStock
            ? (isArabic ? "متوفر الآن" : "In Stock")
            : (isArabic ? "غير متوفر" : "Out of Stock");
        var stockColor = payload.InStock ? "#34D399" : "#F87171";

        var oldPriceText = payload.OldPriceEgp.HasValue ? FormatEgp(payload.OldPriceEgp.Value) : "—";
        var newPriceText = payload.NewPriceEgp.HasValue ? FormatEgp(payload.NewPriceEgp.Value) : "—";

        var savingsHtml = string.Empty;
        if (payload.OldPriceEgp.HasValue && payload.NewPriceEgp.HasValue && payload.OldPriceEgp.Value > payload.NewPriceEgp.Value)
        {
            var diff = payload.OldPriceEgp.Value - payload.NewPriceEgp.Value;
            var pct = payload.OldPriceEgp.Value > 0 ? Math.Round((diff / payload.OldPriceEgp.Value) * 100m, 1) : 0m;
            var saveText = isArabic
                ? $"وفر {FormatEgp(diff)} ({pct}%)"
                : $"Save {FormatEgp(diff)} ({pct}%)";
            savingsHtml = $"""
                <div style="margin-top:8px;display:inline-block;padding:4px 10px;border-radius:999px;background:rgba(52,211,153,0.12);border:1px solid rgba(52,211,153,0.35);color:#34D399;font-size:12px;font-weight:600;">
                  {WebUtility.HtmlEncode(saveText)}
                </div>
                """;
        }

        var footerText = isArabic
            ? "تصلك هذه الرسالة لأنك تتابع هذا اللابتوب في قائمة المفضلة على Egypt Laptop Recommender."
            : "You received this alert because you are watching this laptop in your Egypt Laptop Recommender wishlist.";

        return $$"""
        <!DOCTYPE html>
        <html lang="{{(isArabic ? "ar" : "en")}}" dir="{{dir}}">
        <head>
          <meta charset="utf-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1.0" />
          <title>{{WebUtility.HtmlEncode(BuildPriceAlertSubject(payload))}}</title>
        </head>
        <body style="margin:0;padding:0;background-color:#0A0E13;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#E6EDF3;">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#0A0E13;padding:32px 16px;">
            <tr>
              <td align="center">
                <table role="presentation" width="600" cellspacing="0" cellpadding="0" style="max-width:600px;width:100%;background-color:#10161D;border:1px solid #1E2836;border-radius:14px;overflow:hidden;">
                  <!-- Header -->
                  <tr>
                    <td style="padding:24px 28px;border-bottom:1px solid #1E2836;background-color:#151D27;text-align:{{align}};">
                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                        <tr>
                          <td style="text-align:{{align}};">
                            <span style="font-size:12px;letter-spacing:1.2px;text-transform:uppercase;color:#22D3EE;font-weight:700;">
                              EGYPT LAPTOP RECOMMENDER
                            </span>
                            <div style="margin-top:8px;">
                              <span style="display:inline-block;padding:4px 10px;border-radius:6px;background:{{badgeBg}};color:{{badgeColor}};font-size:11px;font-weight:700;letter-spacing:0.8px;">
                                {{badgeText}}
                              </span>
                            </div>
                          </td>
                        </tr>
                      </table>
                    </td>
                  </tr>

                  <!-- Body -->
                  <tr>
                    <td style="padding:28px;text-align:{{align}};">
                      <p style="margin:0 0 8px 0;font-size:14px;color:#9FB0C3;">{{greeting}}</p>
                      <h1 style="margin:0 0 18px 0;font-size:20px;line-height:1.35;color:#F8FAFC;font-weight:700;">
                        {{headline}}
                      </h1>

                      <!-- Laptop Card -->
                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#151D27;border:1px solid #2B394C;border-radius:10px;padding:20px;">
                        <tr>
                          <td style="padding:20px;text-align:{{align}};">
                            <div style="font-size:17px;font-weight:700;color:#FFFFFF;line-height:1.4;">
                              {{safeTitle}}
                            </div>
                            <div style="margin-top:4px;font-family:'Courier New',monospace;font-size:11px;color:#6E8299;">
                              {{safeCanonicalId}}
                            </div>

                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:18px;border-top:1px solid #1E2836;padding-top:16px;">
                              <tr>
                                <td style="padding:8px 0;vertical-align:top;width:50%;text-align:{{align}};">
                                  <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.6px;color:#8B9BB0;">{{newPriceLabel}}</div>
                                  <div style="margin-top:4px;font-size:24px;font-weight:800;color:#E9B949;">{{newPriceText}}</div>
                                  {{savingsHtml}}
                                </td>
                                <td style="padding:8px 0;vertical-align:top;width:50%;text-align:{{align}};">
                                  <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.6px;color:#8B9BB0;">{{oldPriceLabel}}</div>
                                  <div style="margin-top:6px;font-size:16px;color:#8B9BB0;text-decoration:line-through;">{{oldPriceText}}</div>
                                </td>
                              </tr>
                              <tr>
                                <td style="padding:12px 0 0 0;vertical-align:top;text-align:{{align}};">
                                  <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.6px;color:#8B9BB0;">{{storeLabel}}</div>
                                  <div style="margin-top:4px;font-size:14px;font-weight:600;color:#E6EDF3;">{{safeStore}}</div>
                                </td>
                                <td style="padding:12px 0 0 0;vertical-align:top;text-align:{{align}};">
                                  <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.6px;color:#8B9BB0;">{{stockLabel}}</div>
                                  <div style="margin-top:4px;font-size:14px;font-weight:700;color:{{stockColor}};">{{stockValue}}</div>
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
                    <td style="padding:18px 28px;border-top:1px solid #1E2836;background-color:#0D131A;text-align:{{align}};">
                      <p style="margin:0;font-size:12px;line-height:1.5;color:#6E8299;">
                        {{footerText}}
                      </p>
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

    private static bool IsArabic(string? preferredLanguage)
        => string.Equals(preferredLanguage?.Trim(), "ar", StringComparison.OrdinalIgnoreCase);

    private static string FormatEgp(decimal amount)
        => string.Format(CultureInfo.InvariantCulture, "{0:N0} EGP", amount);
}
