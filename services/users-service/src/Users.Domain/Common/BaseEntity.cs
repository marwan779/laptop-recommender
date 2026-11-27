namespace Users.Domain.Common;

public abstract class BaseEntity
{
    public Guid Id { get; protected set; } = Guid.NewGuid();
    public DateTime CreatedAtUtc { get; protected set; } = DateTime.UtcNow;
    public DateTime? UpdatedAtUtc { get; protected set; }

    public void TouchUpdatedAt(DateTime utcNow)
    {
        UpdatedAtUtc = utcNow;
    }
}
