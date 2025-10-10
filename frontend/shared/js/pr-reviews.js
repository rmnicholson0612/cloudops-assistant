// PR Reviews Functions

// Format AI analysis text with proper HTML structure
function formatAIAnalysisText(text) {
    if (!text) return '';

    // First sanitize the input to prevent XSS
    const sanitizedText = sanitizeHTML(text);

    return sanitizedText
        .replace(/&amp;#39;/g, "'")
        .replace(/&quot;/g, '"')
        .replace(/&amp;/g, '&')
        .replace(/^# (.*$)/gm, '<h2>$1</h2>')
        .replace(/^## (.*$)/gm, '<h3>$1</h3>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/^(\d+\.)\s/gm, '<br><strong>$1</strong> ')
        .replace(/```[\s\S]*?```/g, '')
        .replace(/\n\n/g, '<br><br>')
        .replace(/\n/g, '<br>');
}

// Sanitize HTML to prevent XSS
function sanitizeHTML(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// Format structured analysis object
function formatStructuredAnalysis(analysis) {
    let html = '<div class="structured-analysis">';

    // Risk Level
    if (analysis.risk_level) {
        const riskLevel = sanitizeHTML(analysis.risk_level);
        const riskColor = {'LOW': '#28a745', 'MEDIUM': '#ffc107', 'HIGH': '#dc3545'}[riskLevel] || '#6c757d';
        const riskEmoji = {'LOW': '✅', 'MEDIUM': '⚠️', 'HIGH': '🚨'}[riskLevel] || '⚠️';
        html += `<div style="margin-bottom: 20px;"><h4>${riskEmoji} Risk Assessment</h4>`;
        html += `<p><strong>Risk Level:</strong> <span style="color: ${riskColor}; font-weight: bold;">${riskLevel}</span></p></div>`;
    }

    // Security Issues
    if (analysis.security_issues) {
        html += '<div style="margin-bottom: 20px;"><h4>🔒 Security Issues</h4>';
        if (analysis.security_issues.length > 0) {
            html += '<ul>';
            analysis.security_issues.forEach(issue => {
                html += `<li>${sanitizeHTML(issue)}</li>`;
            });
            html += '</ul>';
        } else {
            html += '<p style="color: #28a745;">✅ No security issues found</p>';
        }
        html += '</div>';
    }

    // Best Practice Violations
    if (analysis.violations) {
        html += '<div style="margin-bottom: 20px;"><h4>⚠️ Best Practice Violations</h4>';
        if (analysis.violations.length > 0) {
            html += '<ul>';
            analysis.violations.forEach(violation => {
                html += `<li>${sanitizeHTML(violation)}</li>`;
            });
            html += '</ul>';
        } else {
            html += '<p style="color: #28a745;">✅ No violations found</p>';
        }
        html += '</div>';
    }

    // Recommendations
    if (analysis.recommendations) {
        html += '<div style="margin-bottom: 20px;"><h4>🛠 Recommendations</h4>';
        if (analysis.recommendations.length > 0) {
            html += '<ul>';
            analysis.recommendations.forEach(rec => {
                html += `<li>${sanitizeHTML(rec)}</li>`;
            });
            html += '</ul>';
        } else {
            html += '<p style="color: #28a745;">✅ No additional recommendations</p>';
        }
        html += '</div>';
    }

    // If no expected fields, show raw data
    if (!analysis.risk_level && !analysis.security_issues && !analysis.violations && !analysis.recommendations) {
        html += '<h4>🔍 Analysis Data</h4><pre style="white-space: pre-wrap; word-wrap: break-word;">' + sanitizeHTML(JSON.stringify(analysis, null, 2)) + '</pre>';
    }

    html += '</div>';
    return html;
}

async function loadPRReviews() {
    const displayElement = document.getElementById('pr-reviews-display');
    const token = localStorage.getItem('access_token');

    if (!token) {
        displayElement.innerHTML = '<div class="pr-error"><i class="fas fa-lock"></i> Please login to view PR reviews</div>';
        return;
    }

    try {
        // Ensure HTTPS for secure connections
        const secureApiUrl = CONFIG.API_BASE_URL.replace(/^http:/, 'https:');
        const response = await fetch(`${secureApiUrl}/pr-reviews`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        const data = await response.json();

        if (response.ok) {
            if (data.reviews.length === 0) {
                displayElement.innerHTML = '<div class="no-pr-reviews">No PR reviews yet. Configure webhooks to get started.</div>';
                return;
            }

            let html = '<div class="pr-reviews-list">';
            data.reviews.forEach(review => {
                const riskColor = {'LOW': '#28a745', 'MEDIUM': '#ffc107', 'HIGH': '#dc3545'}[review.risk_level] || '#6c757d';
                const statusIcon = review.status === 'completed' ? '✅' : review.status === 'failed' ? '❌' : '⏳';

                html += `
                    <div class="pr-review-item" style="cursor: pointer;">
                        <div onclick="console.log('PR clicked:', '${review.review_id}'); showPRReviewDetails('${review.review_id}')" style="position: absolute; top: 0; left: 0; right: 0; bottom: 0; z-index: 1;"></div>
                        <div class="pr-header">
                            <div class="pr-title">
                                <a href="${review.pr_url}" target="_blank" onclick="event.stopPropagation()">${review.pr_title}</a>
                            </div>
                            <div class="pr-meta">
                                <span class="pr-repo">${review.repo_name}</span>
                                <span class="pr-number">#${review.pr_number}</span>
                                <span class="pr-author">by ${review.author}</span>
                            </div>
                        </div>
                        <div class="pr-status">
                            <span class="status">${statusIcon} ${review.status}</span>
                            <span class="risk" style="color: ${riskColor}">Risk: ${review.risk_level}</span>
                            <span class="date">${new Date(review.created_at).toLocaleDateString()}</span>
                        </div>
                    </div>`;
            });
            html += '</div>';

            displayElement.innerHTML = html;
        } else {
            displayElement.innerHTML = `<div class="pr-error">
                <i class="fas fa-exclamation-triangle"></i> Error loading PR reviews: ${data.error}
            </div>`;
        }
    } catch (error) {
        displayElement.innerHTML = `<div class="pr-error">
            <i class="fas fa-times-circle"></i> Failed to load PR reviews
        </div>`;
    }
}

async function showPRReviewDetails(reviewId) {
    const token = localStorage.getItem('access_token');
    if (!token) {
        const displayElement = document.getElementById('pr-reviews-display');
        displayElement.innerHTML = '<div class="pr-error"><i class="fas fa-lock"></i> Please login to view PR review details</div>';
        return;
    }

    try {
        // Ensure HTTPS for secure connections
        const secureApiUrl = CONFIG.API_BASE_URL.replace(/^http:/, 'https:');
        const response = await fetch(`${secureApiUrl}/pr-reviews?review_id=${encodeURIComponent(reviewId)}`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        const data = await response.json();

        if (response.ok) {
            showPRReviewModal(data);
        } else {
            const displayElement = document.getElementById('pr-reviews-display');
            displayElement.innerHTML = `<div class="pr-error"><i class="fas fa-exclamation-triangle"></i> Error loading PR review: ${data.error}</div>`;
        }
    } catch (error) {
        const displayElement = document.getElementById('pr-reviews-display');
        displayElement.innerHTML = '<div class="pr-error"><i class="fas fa-times-circle"></i> Failed to load PR review details</div>';
    }
}

function showPRReviewModal(reviewData) {
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.style.display = 'block';

    const riskColor = {'LOW': '#28a745', 'MEDIUM': '#ffc107', 'HIGH': '#dc3545'}[reviewData.risk_level] || '#6c757d';
    const date = new Date(reviewData.created_at).toLocaleString();

    // Debug: log the actual data structure
    console.log('Full review data:', reviewData);
    console.log('AI review field:', reviewData.ai_review);

    // Parse AI review data
    let analysisHtml = '';
    let aiReview = reviewData.ai_review || reviewData.analysis || reviewData.ai_analysis;

    console.log('AI Review data type:', typeof aiReview);
    console.log('AI Review data:', aiReview);

    if (typeof aiReview === 'string') {
        try {
            aiReview = JSON.parse(aiReview);
            console.log('Parsed AI Review:', aiReview);
        } catch (e) {
            console.log('Failed to parse as JSON, treating as text');
            analysisHtml = formatAIAnalysisText(aiReview);
        }
    }

    // Check if we have a pre-formatted review from backend
    if (reviewData.ai_review_formatted) {
        analysisHtml = formatAIAnalysisText(reviewData.ai_review_formatted);
    } else if (typeof aiReview === 'object' && aiReview) {
        analysisHtml = formatStructuredAnalysis(aiReview);
    }

    if (!analysisHtml) {
        analysisHtml = '<p>No detailed AI analysis available.</p>';
    }

    modal.innerHTML = `
        <div class="modal-content" style="max-width: 900px;">
            <div class="modal-header">
                <h2><i class="fas fa-code-branch"></i> PR Review Analysis</h2>
                <span class="close" onclick="this.closest('.modal').remove()">&times;</span>
            </div>
            <div class="modal-body">
                <div class="pr-review-metadata" style="background: #f8f9fa; padding: 15px; border-radius: 6px; margin-bottom: 20px;">
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
                        <div>
                            <p><strong>Repository:</strong> ${sanitizeHTML(reviewData.repo_name)}</p>
                            <p><strong>PR:</strong> <a href="${sanitizeHTML(reviewData.pr_url)}" target="_blank">#${sanitizeHTML(reviewData.pr_number)} - ${sanitizeHTML(reviewData.pr_title)}</a></p>
                            <p><strong>Author:</strong> ${sanitizeHTML(reviewData.author)}</p>
                        </div>
                        <div>
                            <p><strong>Status:</strong> ${sanitizeHTML(reviewData.status)}</p>
                            <p><strong>Risk Level:</strong> <span style="color: ${riskColor}; font-weight: bold;">${sanitizeHTML(reviewData.risk_level)}</span></p>
                            <p><strong>Analyzed:</strong> ${sanitizeHTML(date)}</p>
                        </div>
                    </div>
                    ${reviewData.comment_posted ?
                        '<p style="color: #28a745; margin-top: 10px;"><i class="fas fa-check"></i> Comment posted to GitHub</p>' :
                        '<p style="color: #dc3545; margin-top: 10px;"><i class="fas fa-times"></i> Comment not posted (no GitHub token)</p>'
                    }
                </div>

                <div class="ai-analysis-content" style="line-height: 1.6; font-size: 14px; padding: 15px; background: #f8f9fa; border-radius: 6px;">
                    <!-- Analysis content will be safely inserted via textContent -->
                </div>

                <div class="pr-actions" style="margin-top: 20px; padding-top: 15px; border-top: 1px solid #dee2e6;">
                    <a href="${sanitizeHTML(reviewData.pr_url)}" target="_blank" class="btn btn-primary">
                        <i class="fab fa-github"></i> View on GitHub
                    </a>
                    <button class="btn btn-secondary" onclick="this.closest('.modal').remove()">
                        Close
                    </button>
                </div>
            </div>
        </div>`;

    document.body.appendChild(modal);

    // Safely insert the analysis content after modal is created
    const analysisContainer = modal.querySelector('.ai-analysis-content');
    if (analysisContainer && analysisHtml) {
        // Always use textContent for safety - no HTML execution
        analysisContainer.textContent = analysisHtml.replace(/<[^>]*>/g, '');
    }
}

function setupWebhookURL() {
    const webhookUrlInput = document.getElementById('webhook-url');
    if (webhookUrlInput && CONFIG.API_BASE_URL) {
        // Ensure HTTPS for secure connections - force HTTPS protocol
        const secureUrl = CONFIG.API_BASE_URL.replace(/^https?:/, 'https:');
        webhookUrlInput.value = `${secureUrl}/pr-webhook`;
    }
}

function copyWebhookURL() {
    const webhookUrlInput = document.getElementById('webhook-url');
    webhookUrlInput.select();
    webhookUrlInput.setSelectionRange(0, 99999);
    document.execCommand('copy');

    // Show feedback
    const button = webhookUrlInput.nextElementSibling;
    const originalText = button.innerHTML;
    button.innerHTML = '<i class="fas fa-check"></i>';
    button.style.color = '#28a745';

    setTimeout(() => {
        button.innerHTML = originalText;
        button.style.color = '';
    }, 2000);
}

// PR Configuration Functions
function showPRConfigModal() {
    document.getElementById('pr-config-modal').style.display = 'block';
}

function closePRConfigModal() {
    document.getElementById('pr-config-modal').style.display = 'none';
}

async function savePRConfig() {
    const repoName = document.getElementById('pr-repo-name').value.trim();
    const githubUrl = document.getElementById('pr-github-url').value.trim();
    const enabled = document.getElementById('pr-enabled').checked;

    if (!repoName || !githubUrl) {
        alert('Repository name and GitHub URL are required');
        return;
    }

    const token = localStorage.getItem('access_token');
    if (!token) {
        alert('Please login to configure PR reviews');
        return;
    }

    try {
        // Ensure HTTPS for secure connections - validate and force HTTPS protocol
        let secureApiUrl = CONFIG.API_BASE_URL;
        if (!secureApiUrl.startsWith('https://')) {
            secureApiUrl = secureApiUrl.replace(/^https?:\/\//, 'https://');
            if (!secureApiUrl.startsWith('https://')) {
                secureApiUrl = 'https://' + secureApiUrl;
            }
        }
        const response = await fetch(`${secureApiUrl}/pr-config`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                repo_name: repoName,
                github_url: githubUrl,
                enabled: enabled
            })
        });

        const data = await response.json();

        if (response.ok) {
            alert('PR review configuration saved successfully!');
            closePRConfigModal();
            loadPRReviews();
        } else {
            alert(`Error: ${data.error}`);
        }
    } catch (error) {
        alert('Failed to save PR configuration');
    }
}

function showPRReviewsInfo() {
    document.getElementById('pr-reviews-info-modal').style.display = 'block';
}

function closePRReviewsInfo() {
    document.getElementById('pr-reviews-info-modal').style.display = 'none';
}
