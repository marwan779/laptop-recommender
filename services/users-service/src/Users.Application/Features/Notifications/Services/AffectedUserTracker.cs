using Users.Application.Common.Interfaces.Jobs;

namespace Users.Application.Features.Notifications.Services;

/// <summary>
/// Collects the distinct users and email alerts affected by an integration event so
/// cache invalidation and background jobs run only after the unit of work commits.
/// </summary>
public sealed class AffectedUserTracker
{
    private readonly HashSet<Guid> _userIds = [];
    private readonly List<PriceAlertEmailJobPayload> _emailAlerts = [];
    private readonly Lock _gate = new();

    public void Track(Guid userId)
    {
        lock (_gate)
        {
            _userIds.Add(userId);
        }
    }

    public void TrackEmailAlert(PriceAlertEmailJobPayload payload)
    {
        lock (_gate)
        {
            _emailAlerts.Add(payload);
        }
    }

    public IReadOnlyCollection<Guid> Snapshot()
    {
        lock (_gate)
        {
            return _userIds.ToArray();
        }
    }

    public IReadOnlyList<PriceAlertEmailJobPayload> SnapshotEmailAlerts()
    {
        lock (_gate)
        {
            return _emailAlerts.ToArray();
        }
    }
}
