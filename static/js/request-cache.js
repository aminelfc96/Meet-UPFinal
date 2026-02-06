/**
 * Request Cache Module
 * Prevents repeated API calls and caches permission results
 */

class RequestCache {
    constructor() {
        this.cache = new Map();
        this.pendingRequests = new Map();
        this.adminStatus = new Map();
        this.defaultTTL = 60000; // 1 minute cache
        this.adminTTL = 300000; // 5 minutes for admin status
    }

    /**
     * Generate cache key for a request
     */
    getCacheKey(url, options = {}) {
        const method = options.method || 'GET';
        const headers = JSON.stringify(options.headers || {});
        return `${method}:${url}:${headers}`;
    }

    /**
     * Check if cache entry is valid
     */
    isValid(entry) {
        return entry && Date.now() < entry.expiry;
    }

    /**
     * Get cached response
     */
    get(url, options = {}) {
        const key = this.getCacheKey(url, options);
        const entry = this.cache.get(key);
        return this.isValid(entry) ? entry.data : null;
    }

    /**
     * Set cached response
     */
    set(url, options = {}, data, ttl = this.defaultTTL) {
        const key = this.getCacheKey(url, options);
        this.cache.set(key, {
            data,
            expiry: Date.now() + ttl
        });
    }

    /**
     * Clear cache entry
     */
    clear(url, options = {}) {
        const key = this.getCacheKey(url, options);
        this.cache.delete(key);
    }

    /**
     * Clear all cache
     */
    clearAll() {
        this.cache.clear();
        this.pendingRequests.clear();
        this.adminStatus.clear();
    }

    /**
     * Cached fetch with deduplication
     */
    async fetch(url, options = {}) {
        const cacheKey = this.getCacheKey(url, options);
        
        // Return cached response if available
        const cached = this.get(url, options);
        if (cached) {
            return { ...cached, fromCache: true };
        }

        // Check if request is already in flight
        if (this.pendingRequests.has(cacheKey)) {
            return this.pendingRequests.get(cacheKey);
        }

        // Make the request
        const promise = this._makeRequest(url, options, cacheKey);
        this.pendingRequests.set(cacheKey, promise);

        return promise;
    }

    async _makeRequest(url, options, cacheKey) {
        try {
            const response = await fetch(url, options);
            const data = {
                ok: response.ok,
                status: response.status,
                statusText: response.statusText,
                headers: Object.fromEntries(response.headers.entries()),
                data: response.ok ? await response.json() : null
            };

            // Cache successful responses
            if (response.ok) {
                const ttl = url.includes('/pending') ? this.adminTTL : this.defaultTTL;
                this.set(url, options, data, ttl);
            }

            return data;
        } catch (error) {
            throw error;
        } finally {
            this.pendingRequests.delete(cacheKey);
        }
    }

    /**
     * Check and cache admin status
     */
    async checkAdminStatus(teamId, authToken) {
        const cacheKey = `admin:${teamId}`;
        
        // Return cached admin status if available
        const cached = this.adminStatus.get(cacheKey);
        if (cached && Date.now() < cached.expiry) {
            return cached.isAdmin;
        }

        try {
            const response = await this.fetch(`/api/teams/${teamId}/pending`, {
                headers: { 'Authorization': `Bearer ${authToken}` }
            });

            const isAdmin = response.ok && response.status !== 403;
            
            // Cache admin status
            this.adminStatus.set(cacheKey, {
                isAdmin,
                expiry: Date.now() + this.adminTTL
            });

            return isAdmin;
        } catch (error) {
            // Cache negative result for shorter time to retry sooner
            this.adminStatus.set(cacheKey, {
                isAdmin: false,
                expiry: Date.now() + 30000 // 30 seconds
            });
            return false;
        }
    }

    /**
     * Get pending requests with caching
     */
    async getPendingRequests(teamId, authToken) {
        // Check admin status first
        const isAdmin = await this.checkAdminStatus(teamId, authToken);
        if (!isAdmin) {
            return { isAdmin: false, requests: [] };
        }

        try {
            const response = await this.fetch(`/api/teams/${teamId}/pending`, {
                headers: { 'Authorization': `Bearer ${authToken}` }
            });

            if (response.ok) {
                return { isAdmin: true, requests: response.data || [] };
            }
            return { isAdmin: false, requests: [] };
        } catch (error) {
            console.error('Error fetching pending requests:', error);
            return { isAdmin: false, requests: [] };
        }
    }

    /**
     * Invalidate cache for team-related operations
     */
    invalidateTeamCache(teamId) {
        const keysToDelete = [];
        for (const key of this.cache.keys()) {
            if (key.includes(`/teams/${teamId}/`) || key.includes(`/user/teams`)) {
                keysToDelete.push(key);
            }
        }
        keysToDelete.forEach(key => this.cache.delete(key));
        
        // Also clear admin status
        this.adminStatus.delete(`admin:${teamId}`);
    }
}

// Create global cache instance
window.requestCache = new RequestCache();

// Clear cache on authentication changes
if (typeof authToken !== 'undefined') {
    let lastToken = authToken;
    setInterval(() => {
        if (authToken !== lastToken) {
            window.requestCache.clearAll();
            lastToken = authToken;
        }
    }, 1000);
}