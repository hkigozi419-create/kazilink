// KaziLink live Supabase REST helper (public read operations only)
window.KaziLinkLive = (() => {
  const c = window.KAZILINK_SUPABASE;
  if (!c) return { enabled: false };

  const headers = {
    apikey: c.publishableKey,
    Authorization: `Bearer ${c.publishableKey}`
  };

  async function get(path) {
    const r = await fetch(c.url + '/rest/v1/' + path, { headers });
    if (!r.ok) throw new Error('Supabase request failed');
    return r.json();
  }

  async function workers(trade = '', location = '') {
    const users = await get(
      'users?select=id,name,phone,location&role=eq.worker'
    );

    if (!users.length) return [];

    const wantedLocation = String(location || '').trim().toLowerCase();
    const wantedTrade = String(trade || '').trim().toLowerCase();

    const locationMatches = users.filter(u => {
      if (!wantedLocation) return true;

      const saved = String(u.location || '').trim().toLowerCase();

      return (
        saved.includes(wantedLocation) ||
        wantedLocation.includes(saved)
      );
    });

    if (!locationMatches.length) return [];

    const ids = locationMatches.map(x => x.id).join(',');

    const profiles = await get(
      'worker_profiles?select=*&user_id=in.(' + ids + ')'
    );

    const byId = Object.fromEntries(
      profiles.map(x => [x.user_id, x])
    );

    return locationMatches
      .filter(u => byId[u.id])
      .map(u => ({
        ...u,
        ...byId[u.id],
        user_id: u.id
      }))
      .filter(w => {
        if (!wantedTrade) return true;

        const workerTrade = String(w.trade || '').toLowerCase();

        return (
          workerTrade.includes(wantedTrade) ||
          wantedTrade.includes(workerTrade)
        );
      });
  }

  async function openJobs() {
    return get(
      'jobs?select=*&status=eq.open&order=created_at.desc'
    );
  }

  return {
    enabled: true,
    workers,
    openJobs
  };
})();
