export function localReviewDate(now = new Date()): string {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function activityKey(ownerSubject: string): string {
  return `review_practiced_on_v1:${encodeURIComponent(ownerSubject)}`;
}

export function hasPracticedToday(
  ownerSubject: string,
  now = new Date(),
): boolean {
  try {
    return (
      localStorage.getItem(activityKey(ownerSubject)) === localReviewDate(now)
    );
  } catch {
    return false;
  }
}

export function markPracticedToday(ownerSubject: string): void {
  try {
    localStorage.setItem(activityKey(ownerSubject), localReviewDate());
  } catch {
    return;
  }
}
