// Code Reviews App Module

function initializeCodeReviews() {
    // Initialize any default state
}

async function loadPRReviews() {
    if (!API.requireAuth()) return;

    const display = document.getElementById('pr-reviews');
    display.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading PR reviews...';

    try {
        const response = await API.get('/reviews/list');
        displayPRReviews(response.reviews || []);
    } catch (error) {
        display.innerHTML = `<p>Error loading reviews: ${error.message}</p>`;
    }
}

function displayPRReviews(reviews) {
    const display = document.getElementById('pr-reviews');

    if (!reviews || reviews.length === 0) {
        display.innerHTML = '<p>No PR reviews found.</p>';
        return;
    }

    display.innerHTML = `
        <div class="reviews-list">
            ${reviews.map(review => `
                <div class="review-item">
                    <h5>${review.repository}</h5>
                    <p>PR #${review.pr_number}: ${review.title}</p>
                    <p>Status: ${review.status}</p>
                </div>
            `).join('')}
        </div>
    `;
}
