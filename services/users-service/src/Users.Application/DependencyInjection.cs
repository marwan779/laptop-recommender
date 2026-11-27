using Microsoft.Extensions.DependencyInjection;
using Users.Application.Common.Interfaces.Messaging;
using Users.Application.Features.Admin.Services;
using Users.Application.Features.Auth.Services;
using Users.Application.Features.Notifications.Events;
using Users.Application.Features.Notifications.Handlers;
using Users.Application.Features.Notifications.Services;
using Users.Application.Features.Wishlist.Services;

namespace Users.Application;

public static class DependencyInjection
{
    public static IServiceCollection AddApplication(this IServiceCollection services)
    {
        services.AddScoped<IAuthService, AuthService>();
        services.AddScoped<IAdminUsersService, AdminUsersService>();
        services.AddScoped<IWishlistService, WishlistService>();
        services.AddScoped<INotificationService, NotificationService>();
        services.AddScoped<AffectedUserTracker>();
        services.AddScoped<IIntegrationEventHandler<LaptopPriceChangedBatchEvent>, LaptopPriceChangedHandler>();
        return services;
    }
}
