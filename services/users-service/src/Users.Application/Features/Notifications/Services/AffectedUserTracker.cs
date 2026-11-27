namespace Users.Application.Features.Notifications.Services;

/// <summary>
/// Collects the distinct users affected by an integration event so cache
/// invalidation can run after the surrounding unit of work commits.
/// </summary>
public sealed class AffectedUserTracker
{
    private readonly HashSet<Guid> _userIds = [];
    private readonly Lock _gate = new();

    public void Track(Guid userId)
    {
        lock (_gate)
        {
            _userIds.Add(userId);
        }
    }

    public IReadOnlyCollection<Guid> Snapshot()
    {
        lock (_gate)
        {
            return _userIds.ToArray();
        }
    }
}
