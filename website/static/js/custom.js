document.addEventListener('DOMContentLoaded', function() {
    // Court-related functionality
    const courtNumber = document.getElementById('court-number');
    if (courtNumber) {
        // Initialize Flatpickr
        flatpickr("#date_NonStop", {
            enableTime: true,
            dateFormat: "Y-m-d H:i",
            time_24hr: true,
            minuteIncrement: 15,
            onChange: function(selectedDates, dateStr, instance) {
                const formContainer = document.getElementById('form-container');
                if (!formContainer) return;

                // Check if the selected date is not empty
                if (selectedDates.length > 0) {
                    // Get selected date and time
                    const dateStart = new Date(selectedDates[0]);
                    const dateEnd = new Date(dateStart.getTime() + 120 * 60000); // 120 minutes in milliseconds

                    // Send an AJAX request to check for matches and update court visibility
                    $.ajax({
                        type: 'POST',
                        url: '/checkMatches',
                        data: {
                            dateStart: dateStart.toISOString(),
                            dateEnd: dateEnd.toISOString()
                        },
                        success: function(response) {
                            // Update the court visibility based on the response
                            updateCourtVisibility(response);
                        },
                        error: function(error) {
                            console.log(error);
                        }
                    });

                    formContainer.style.display = 'block';
                } else {
                    formContainer.style.display = 'none';
                }
            }
        });

        // Event listener for court number dropdown
        courtNumber.addEventListener('change', function () {
            const selectedValue = parseInt(this.value);

            // Update court display
            updateCourtDisplay(selectedValue);

            // Update nonStop_duration dropdown based on court-number
            updateNonStopDurationDropdown(selectedValue);
        });
    }

    // Event listener for court cards
    const courtElements = document.querySelectorAll('.Court');
    if (courtElements.length > 0) {
        courtElements.forEach(court => {
            court.addEventListener('click', function () {
                const isAlreadySelected = court.classList.contains('selectedCourt');
                const selectedCourts = document.querySelectorAll('.selectedCourt');
                const selectedValue = parseInt(document.getElementById('court-number').value);

                if ((selectedCourts.length < selectedValue || isAlreadySelected) && !court.classList.contains('disabledCourt')) {
                    court.classList.toggle('selectedCourt', !isAlreadySelected);

                    // Update selected count label and total number of players
                    updateSelectedCountLabel();
                    updateTotalPlayers(selectedValue);
                } else {
                    alert(`You can only select ${selectedValue} court(s).`);
                }
            });
        });
    }

    // Event listener for nonStop_duration dropdown
    const nonStopDuration = document.getElementById('nonStop_duration');
    if (nonStopDuration) {
        nonStopDuration.addEventListener('change', function () {
            const selectedValue = parseInt(this.value);
            const courtNumber = parseInt(document.getElementById('court-number').value);

            // Allow changing the value only if court-number is 2 or 3
            if (courtNumber === 2 || courtNumber === 3) {
                // Set default values 90 or 120 for court-number 2 or 3
                if (selectedValue !== 90 && selectedValue !== 120) {
                    this.value = 90;
                }
            } else {
                // Set default value 120 for court-number 4 and disable changing
                this.value = 120;
            }
        });
    }

    // League creation court selection handling
    const leagueCourtCheckboxes = document.querySelectorAll('.court-checkbox');
    const leagueCourtCards = document.querySelectorAll('.court-card');
    if (leagueCourtCheckboxes.length > 0 && leagueCourtCards.length > 0) {
        // Toggle League Info box if it exists
        const toggleLeagueInfoBtn = document.getElementById('toggleLeagueInfo');
        const leagueInfoBox = document.getElementById('leagueInfoBox');
        
        if (toggleLeagueInfoBtn && leagueInfoBox) {
            toggleLeagueInfoBtn.addEventListener('click', function() {
                $(leagueInfoBox).collapse('toggle');
            });
        }
        
        // Update court card appearance based on checkbox state
        function updateCardAppearance(checkbox, card) {
            if (checkbox.checked) {
                card.classList.add('selected');
            } else {
                card.classList.remove('selected');
            }
        }
        
        // Add event listeners for league court checkboxes
        leagueCourtCheckboxes.forEach((checkbox, index) => {
            const card = leagueCourtCards[index];
            
            // Initial state
            updateCardAppearance(checkbox, card);
            
            // Listen for changes
            checkbox.addEventListener('change', function() {
                updateCardAppearance(this, card);
                validateCourts();
            });
            
            // Make the entire card clickable
            card.addEventListener('click', function(e) {
                // Prevent clicking the card from triggering if user is clicking the checkbox directly
                if (e.target !== checkbox && e.target.tagName.toLowerCase() !== 'label') {
                    checkbox.checked = !checkbox.checked;
                    updateCardAppearance(checkbox, card);
                    validateCourts();
                    
                    // Create a change event to ensure any other event handlers run
                    checkbox.dispatchEvent(new Event('change'));
                }
            });
        });
        
        // Validate court selection for league creation
        function validateCourts() {
            const submitButton = document.getElementById('submitButton');
            if (!submitButton) return;
            
            const nbTeams = parseInt(document.querySelector('input[name="league_id"]').getAttribute('data-teams') || 0);
            const requiredCourts = Math.ceil(nbTeams / 2);
            const selectedCourts = document.querySelectorAll('.court-checkbox:checked').length;
            
            submitButton.disabled = selectedCourts !== requiredCourts;
            return selectedCourts === requiredCourts;
        }
    }

    const addToCartButtons = document.querySelectorAll('.btn-add-to-cart');
    if (addToCartButtons.length > 0) {
        addToCartButtons.forEach(button => {
            button.addEventListener('click', function(event) {
                event.preventDefault();
                const url = this.getAttribute('href');
                fetch(url, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCookie('csrf_token')
                    }
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert('Package added to cart');
                    } else {
                        alert('Failed to add package to cart');
                    }
                });
            });
        });
    }
});

// User profile photo click handler
document.addEventListener('DOMContentLoaded', function() {
    const userPhotoImg = document.getElementById('user_photo_img');
    const userPhotoInput = document.getElementById('user_photo');
    
    if (!userPhotoImg || !userPhotoInput) return; // Only run on user profile pages
    
    userPhotoImg.addEventListener('click', function() {
        userPhotoInput.click();
    });
});

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Function to update court display based on selected value
function updateCourtDisplay(selectedValue) {
    const courtElements = document.querySelectorAll('.Court');
    if (!courtElements.length) return;

    courtElements.forEach((court, index) => {
        court.classList.remove('selectedCourt', 'disabledCourt');
    });

    // Update selected count label and total number of players
    updateSelectedCountLabel();
    updateTotalPlayers(selectedValue);
}

// Function to update the selected count label
function updateSelectedCountLabel() {
    const selectedCourts = document.querySelectorAll('.selectedCourt');
    const selectedCountLabel = document.getElementById('selectedCountLabel');
    if (!selectedCountLabel) return;

    const selectedValue = parseInt(document.getElementById('court-number').value);

    if (selectedCourts.length > selectedValue) {
        selectedCourts.forEach(selectedCourt => {
            selectedCourt.classList.remove('selectedCourt');
        });

        alert(`You can only select ${selectedValue} court(s).`);
    }

    selectedCountLabel.textContent = `${selectedCourts.length} court${selectedCourts.length !== 1 ? 's' : ''} selected`;
}

// Function to update total number of players
function updateTotalPlayers(selectedValue) {
    const numPlayerTotal = document.getElementById('num_player_total');
    if (numPlayerTotal) {
        numPlayerTotal.value = selectedValue * 4;
    }
}

// Function to update nonStop_duration dropdown based on court-number
function updateNonStopDurationDropdown(courtNumber) {
    const nonStopDurationDropdown = document.getElementById('nonStop_duration');
    if (!nonStopDurationDropdown) return;

    // Set default values 90 or 120 for court-number 2 or 3
    // Set default value 120 and disable changing for court-number 4
    if (courtNumber === 2 || courtNumber === 3) {
        nonStopDurationDropdown.value = 90;
        nonStopDurationDropdown.removeAttribute('disabled');
    } else {
        nonStopDurationDropdown.value = 120;
        nonStopDurationDropdown.setAttribute('disabled', 'disabled');
    }
}

// Gameday edit form handling
$(document).ready(function() {
    var $form = $('#editGameDayForm');
    var $dateInput = $('#date');
    var originalDate = $('input[name="original_date"]').val();
    var $updateSubsequent = $('#update_subsequent');
    
    $form.on('submit', function(e) {
        e.preventDefault();
        
        if ($dateInput.val() !== originalDate) {
            Swal.fire({
                title: 'Confirm Update',
                text: 'Do you want to update the dates of all subsequent game days?',
                icon: 'question',
                showCancelButton: true,
                confirmButtonText: 'Yes',
                cancelButtonText: 'No',
                reverseButtons: true
            }).then((result) => {
                if (result.isConfirmed) {
                    $updateSubsequent.val('true');
                } else {
                    $updateSubsequent.val('false');
                }
                $form[0].submit();
            });
        } else {
            this.submit();
        }
    });
});

// Create League Form Functionality 
document.addEventListener('DOMContentLoaded', function() {
    const clubSelect = document.getElementById('club_id');
    const nbTeamsInput = document.getElementById('nbr_teams');
    const submitButton = document.getElementById('submitButton');
    const form = document.getElementById('leagueForm');
    const courtWarningDiv = document.getElementById('court-warning');
    const courtWarningMessage = document.getElementById('court-warning-message');
    
    if (!form) return; // Only run this code on create league page
    
    // Validate the form
    function validateForm() {
        const clubId = clubSelect.value;
        const clubOption = document.querySelector(`option[value="${clubId}"]`);
        const totalCourts = parseInt(clubOption?.dataset.courts || 0);
        const nbrTeams = parseInt(nbTeamsInput.value, 10) || 0;
        const requiredCourts = Math.ceil(nbrTeams / 2);
        
        // Update warning message
        if (totalCourts === 0) {
            courtWarningMessage.textContent = translate('The selected club does not have any courts. Please add courts to the club first.');
            courtWarningDiv.style.display = 'block';
            submitButton.disabled = true;
            return false;
        } else if (nbrTeams > 0 && requiredCourts > totalCourts) {
            courtWarningMessage.textContent = translate('The selected club does not have enough courts. You need ' + requiredCourts + ' courts for ' + nbrTeams + ' teams, but this club only has ' + totalCourts + ' courts.');
            courtWarningDiv.style.display = 'block';
            submitButton.disabled = true;
            return false;
        } else {
            courtWarningDiv.style.display = 'none';
            if (nbrTeams > 0) {
                submitButton.disabled = false;
                return true;
            } else {
                submitButton.disabled = true;
                return false;
            }
        }
    }
    
    // Event listeners
    clubSelect.addEventListener('change', validateForm);
    nbTeamsInput.addEventListener('change', validateForm);
    nbTeamsInput.addEventListener('input', validateForm);
    
    form.addEventListener('submit', function(event) {
        if (!validateForm()) {
            event.preventDefault();
        }
    });
    
    // Initial setup
    validateForm();
});

// Edit League Form Functionality
document.addEventListener('DOMContentLoaded', function() {
    const clubSelect = document.getElementById('club_id');
    const nbTeamsInput = document.getElementById('nbr_teams');
    const basicInfoForm = document.getElementById('basicInfoForm');
    
    if (!basicInfoForm) return; // Only run on edit league page
    
    function validateForm() {
        const clubId = clubSelect.value;
        const clubOption = document.querySelector(`option[value="${clubId}"]`);
        const totalCourts = parseInt(clubOption?.dataset.courts || 0);
        const nbrTeams = parseInt(nbTeamsInput.value, 10) || 0;
        const requiredCourts = Math.ceil(nbrTeams / 2);
        
        if (totalCourts < requiredCourts) {
            alert(translate('Warning: The selected club needs at least ' + requiredCourts + ' courts for ' + nbrTeams + ' teams'));
            return false;
        }
        return true;
    }
    
    basicInfoForm.addEventListener('submit', function(event) {
        if (!validateForm()) {
            event.preventDefault();
        }
    });
    
    // Keep the active tab after form submission
    const hash = window.location.hash;
    if (hash) {
        $('.nav-tabs a[href="' + hash + '"]').tab('show');
    }
    
    // Update URL hash when tab changes
    $('.nav-tabs a').on('shown.bs.tab', function (e) {
        window.location.hash = e.target.hash;
    });

    // Handle accordion state in URL
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('edit') === 'true') {
        $('#editLeagueContent').collapse('show');
    }
    
    // Update URL when accordion changes
    $('#editLeagueContent').on('shown.bs.collapse', function () {
        const url = new URL(window.location.href);
        url.searchParams.set('edit', 'true');
        window.history.pushState({}, '', url);
    });
    
    $('#editLeagueContent').on('hidden.bs.collapse', function () {
        const url = new URL(window.location.href);
        url.searchParams.delete('edit');
        window.history.pushState({}, '', url);
    });
});

// Club User Search and Add User Event Form Functionality
$(document).ready(function() {
    const userEmail = $('#user_email, #fullname');  // Added fullname selector
    const userSuggestions = $('#userSuggestions');
    
    if (!userEmail.length || !userSuggestions.length) return; // Only run on pages with user search
    
    let debounceTimer;

    userEmail.on('input', function(e) {
        clearTimeout(debounceTimer);
        const query = $(this).val().trim();
        const inputField = $(this);
        
        if (query.length < 3) {
            userSuggestions.hide();
            return;
        }

        debounceTimer = setTimeout(() => {
            $.get('/search_users', { query: query })
                .done(function(users) {
                    if (users && users.length > 0) {
                        const html = users.map(user => `
                            <div class="suggestion-item p-2 text-white d-flex align-items-center" 
                                 data-email="${user.email}"
                                 data-name="${user.name}"
                                 data-telephone="${user.telephone}"
                                 data-user-id="${user.id}"
                                 style="cursor: pointer; background-color: #2d3245; white-space: nowrap; overflow: hidden;">
                                <img src="/display_user_image/${user.id}" 
                                     alt="${user.name}" 
                                     class="rounded-circle mr-2" 
                                     width="32" 
                                     height="32" 
                                     style="object-fit: cover;">
                                <span style="display: inline-block; min-width: 200px;">${highlightMatch(user.name, query)}</span>
                                <span style="display: inline-block; margin: 0 8px; color: rgba(255,255,255,0.5);">-</span>
                                <span style="display: inline-block; color: rgba(255,255,255,0.7);">${user.telephone}</span>
                                <span style="display: inline-block; margin: 0 8px; color: rgba(255,255,255,0.5);">-</span>
                                <span style="display: inline-block; color: rgba(255,255,255,0.7);">${user.email}</span>
                            </div>
                        `).join('');

                        userSuggestions
                            .html(html)
                            .show()
                            .css({
                                'background-color': '#2d3245',
                                'border': '1px solid rgba(255, 255, 255, 0.15)',
                                'border-top': 'none',
                                'max-height': '200px',
                                'overflow-y': 'auto',
                                'overflow-x': 'hidden',
                                'z-index': '1050'  // Make sure suggestions appear above other elements
                            });

                        // Add hover effect
                        $('.suggestion-item').hover(
                            function() { $(this).css('background-color', '#3d4255'); },
                            function() { $(this).css('background-color', '#2d3245'); }
                        );
                    } else {
                        userSuggestions.hide();
                    }
                });
        }, 300);
    });

    userSuggestions.on('click', '.suggestion-item', function(e) {
        e.preventDefault();
        e.stopPropagation();
        
        const email = $(this).data('email');
        const name = $(this).data('name');
        const telephone = $(this).data('telephone');
        const userId = $(this).data('user-id');
        
        // Check if we're in the add user event form
        if ($('#fullname').length > 0) {
            $('#fullname').val(name);
            $('#email').val(email).prop('readonly', true);
            $('#telephone').val(telephone).prop('readonly', true);
            $('#user_id').val(userId);
            $('#clearButton').show(); // Show clear button when suggestion is selected
        } else {
            // We're in the club user form
            $('#user_email').val(email);
        }
        userSuggestions.hide();
    });

    // Add clear button handler
    $('#clearButton').on('click', function() {
        $('#fullname').val('');
        $('#email').val('').prop('readonly', false);
        $('#telephone').val('').prop('readonly', false);
        $('#user_id').val('');
        $('#photo').val('');
        $(this).hide();
    });

    // Add input handler to enable editing when fields are cleared
    $('#fullname').on('input', function() {
        if (!$(this).val()) {
            $('#email').prop('readonly', false).val('');
            $('#telephone').prop('readonly', false).val('');
            $('#user_id').val('');
            $('#clearButton').hide(); // Hide clear button when name is cleared
        }
    });

    // Hide suggestions when clicking outside
    $(document).on('click', function(e) {
        if (!$(e.target).closest('.form-group').length) {
            userSuggestions.hide();
        }
    });

    // Form submission handling
    userEmail.closest('form').on('submit', function(e) {
        const emailInput = userEmail.val().trim();
        if (!emailInput) {
            e.preventDefault();
            alert(translate("Please enter a name or select from the suggestions"));
            return;
        }
    });
});

function highlightMatch(text, query) {
    if (!text) return '';
    const lowerText = text.toLowerCase();
    const lowerQuery = query.toLowerCase();
    
    const queryWords = lowerQuery.split(/\s+/).filter(word => word.length > 0);
    let result = text;
    
    queryWords.forEach(word => {
        if (word.length >= 2) {  // Only highlight words with 2 or more characters
            const regex = new RegExp('(' + word + ')', 'gi');
            result = result.replace(regex, '<strong class="text-primary">$1</strong>');
        }
    });
    
    return result;
}

// Note deletion functionality 
function deleteNote(noteId) {
    fetch("/delete-note", {
        method: "POST",
        body: JSON.stringify({ noteId: noteId }),
    }).then((_res) => {
        window.location.href = "/";
    });
}

// Table row navigation
$(document.body).on("click", "tr[data-href]", function () {
    window.location.href = this.dataset.href;
});

// Language switcher
function changeLanguage(lang) {
    document.cookie = `lang=${lang}; path=/`;
    const url = new URL(window.location.href);
    url.searchParams.set('lang', lang);
    window.location.href = url.toString();
}

// Search bar toggle for mobile
document.addEventListener('DOMContentLoaded', function() {
    const toggleSearch = document.querySelector('.toggle-search');
    if (!toggleSearch) return; // Only run if toggle search exists
    
    toggleSearch.addEventListener('click', function() {
        const searchBar = document.querySelector('.search-bar');
        if (searchBar.style.display === 'none' || searchBar.style.display === '') {
            searchBar.style.display = 'block';
        } else {
            searchBar.style.display = 'none';
        }
    });
});

