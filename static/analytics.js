/**
 * Page Analytics Tracker
 * Lightweight behavior tracking for demo/testing
 * Persists to localStorage + sends to backend
 */

class PageAnalytics {
  constructor() {
    this.sessionId = this.getOrCreateSessionId();
    this.pageStartTime = Date.now();
    this.currentPage = window.location.pathname;
    this.events = [];
    this.init();
  }

  getOrCreateSessionId() {
    let sessionId = localStorage.getItem('analytics_session_id');
    if (!sessionId) {
      sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
      localStorage.setItem('analytics_session_id', sessionId);
    }
    return sessionId;
  }

  init() {
    // Track page view
    this.trackPageView();

    // Track clicks
    document.addEventListener('click', (e) => this.trackClick(e));

    // Track form submissions
    document.addEventListener('submit', (e) => this.trackFormSubmit(e));

    // Track input changes
    document.addEventListener('change', (e) => this.trackInputChange(e));

    // Track navigation
    window.addEventListener('beforeunload', () => this.trackPageExit());

    // Save events periodically
    setInterval(() => this.saveEventsLocally(), 30000); // Every 30s

    // Send to server periodically
    setInterval(() => this.sendToServer(), 60000); // Every 60s
  }

  trackPageView() {
    const event = {
      type: 'page_view',
      page: this.currentPage,
      timestamp: Date.now(),
      title: document.title,
      referrer: document.referrer || 'direct',
      userAgent: navigator.userAgent
    };
    this.events.push(event);
    console.log('📊 Page view tracked:', event.page);
  }

  trackClick(e) {
    const target = e.target;
    const event = {
      type: 'click',
      page: this.currentPage,
      timestamp: Date.now(),
      element: target.tagName,
      text: (target.textContent || '').substring(0, 100),
      id: target.id || null,
      class: target.className || null,
      href: target.href || null
    };
    this.events.push(event);
  }

  trackFormSubmit(e) {
    const form = e.target;
    const event = {
      type: 'form_submit',
      page: this.currentPage,
      timestamp: Date.now(),
      formName: form.name || form.id || 'unnamed',
      formId: form.id || null,
      fieldCount: form.querySelectorAll('input, textarea, select').length
    };
    this.events.push(event);
    console.log('📋 Form submitted:', event.formName);
  }

  trackInputChange(e) {
    const target = e.target;
    if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT') {
      const event = {
        type: 'input_change',
        page: this.currentPage,
        timestamp: Date.now(),
        fieldName: target.name || target.id || 'unnamed',
        fieldType: target.type || target.tagName
      };
      this.events.push(event);
    }
  }

  trackPageExit() {
    const timeOnPage = Math.round((Date.now() - this.pageStartTime) / 1000);
    const event = {
      type: 'page_exit',
      page: this.currentPage,
      timestamp: Date.now(),
      timeOnPageSeconds: timeOnPage,
      eventCount: this.events.filter(e => e.page === this.currentPage).length
    };
    this.events.push(event);
    this.saveEventsLocally();
  }

  saveEventsLocally() {
    try {
      const stored = localStorage.getItem('analytics_events') ? JSON.parse(localStorage.getItem('analytics_events')) : [];
      const combined = [...stored, ...this.events];
      // Keep last 1000 events
      const trimmed = combined.slice(-1000);
      localStorage.setItem('analytics_events', JSON.stringify(trimmed));
      this.events = [];
    } catch (e) {
      console.warn('Failed to save events locally:', e);
    }
  }

  sendToServer() {
    try {
      const stored = localStorage.getItem('analytics_events');
      if (!stored) return;

      const events = JSON.parse(stored);
      if (events.length === 0) return;

      fetch('/api/analytics/events', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          sessionId: this.sessionId,
          events: events
        })
      }).then(r => {
        if (r.ok) {
          // Clear sent events
          localStorage.removeItem('analytics_events');
        }
      }).catch(e => console.warn('Failed to send analytics:', e));
    } catch (e) {
      console.warn('Error sending analytics:', e);
    }
  }

  // Public API for manual tracking
  trackEvent(eventType, data = {}) {
    const event = {
      type: eventType,
      page: this.currentPage,
      timestamp: Date.now(),
      ...data
    };
    this.events.push(event);
  }

  getSessionStats() {
    const stored = localStorage.getItem('analytics_events');
    const events = stored ? JSON.parse(stored) : [];
    return {
      sessionId: this.sessionId,
      eventCount: events.length,
      pages: [...new Set(events.map(e => e.page))],
      firstEvent: events[0]?.timestamp,
      lastEvent: events[events.length - 1]?.timestamp
    };
  }
}

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    window.pageAnalytics = new PageAnalytics();
  });
} else {
  window.pageAnalytics = new PageAnalytics();
}
