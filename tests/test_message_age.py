import pytest

from backend.services.age import message_age_months


@pytest.mark.parametrize("message,months", [
    ("My one-month-old baby needs vaccine information for the next six months.", 1),
    ("My 1-month-old baby needs vaccine information for the next 6 months.", 1),
    ("Play ideas for my twenty-four-month-old child?", 24),
    ("My baby is twenty five months old.", 25),
    ("Our child called Amani is eighteen months.", 18),
    ("My baby is three weeks old.", 21 / 30.4375),
    ("My one-day baby needs a vaccine schedule for the next nine months.", 1 / 30.4375),
    ("My baby is one hundred and twenty days old.", 120 / 30.4375),
    ("My two-year-old toddler needs play ideas.", 24),
    ("My baby is 1.5 years old.", 18),
    ("My baby is one and a half years old.", 18),
    ("My baby is two and a half years old.", 30),
    ("My baby is half a year old.", 6),
    ("My baby is a month old.", 1),
    ("She is eighteen months. What play is suitable?", 18),
    ("He's one month. How can we play?", 1),
    ("She's eighteen months.", 18),
    ("Baby is six weeks. How can I talk while feeding?", 42 / 30.4375),
    ("My child turned one year. What play can we try?", 12),
    ("Vaccines for my new born baby for the next nine months?", 0),
    ("Vaccines for my newborn baby for the next 9 months?", 0),
    ("A two\u2011month\u2011old baby needs play ideas.", 2),
    ("The child I mean is two years and three months; can you propose an indoor obstacle game?", 27),
    ("My child is one year and five months old.", 17),
    ("My daughter is one year and seven months. Suggest calm play.", 19),
    ("My son is eleven weeks old.", 77 / 30.4375),
    ("I am twenty-nine years old; my child is seventeen months. Suggest a simple arrival routine for nursery.", 17),
    ("The leaflet says 'activities for a three-year-old', but I am asking about my ten-month-old. How can we explore textures safely?", 10),
    ("Our little girl is seven months; she rolls away during a nappy change.", 7),
    ("My son has just turned fourteen months. How can I help him try a spoon?", 14),
    ("Our little one recently turned nine months. She drops her cup.", 9),
    ("No, I meant seventeen months, not seven months.", 17),
    ("My daughter is now thirteen months. She dislikes having her nails trimmed.", 13),
    ("My baby is not a newborn; she is eighteen months old.", 18),
])
def test_word_and_digit_ages_share_subject_parsing(message, months):
    assert message_age_months(message) == pytest.approx(months)


@pytest.mark.parametrize("message", [
    "Plan vaccines for my baby for the next six months.",
    "I have one toy and six books for my baby.",
    "My baby drinks one hundred and twenty ml.",
    "My baby is one month old and my other child is eighteen months old.",
    "My baby is twenty-six months old and another is six months old.",
    "A handout says a six-month-old can try a cup. How does that apply to my baby?",
    "The website describes an eight-month-old. Is that suitable for my daughter?",
    "When she was four months old she liked this toy. What should I offer now?",
    "My child will be a twelve-month-old in winter. What should we plan?",
    "My baby is not ten months old.",
    "My child isn't a nineteen-month-old.",
    "I'm twenty-seven years old and have a baby. How can we share a book?",
    "I am a twenty-nine-year-old first-time mum. What should I note before a clinic visit?",
    "His mother is twenty-two years old. How can she help him settle?",
    "I am twenty-six years old and have a baby. How can I soothe her?",
    "My partner is twenty-five years old. Our baby keeps pulling her hair.",
    "I am a twenty-eight-year-old mother. How can I share a book with my baby?",
    "My baby is not a newborn. How can we play?",
    "An article about a newborn baby worries me. What should I ask at the clinic?",
    "My child was three months old when this began. How can I help now?",
    "My daughter was a newborn when this began. How can I help now?",
])
def test_durations_counts_and_ambiguous_ages_do_not_become_one_child_age(message):
    assert message_age_months(message) is None


@pytest.mark.parametrize("subject", ["Our little girl", "My son", "Our little one"])
@pytest.mark.parametrize("state", ["is now", "has just turned", "recently turned"])
@pytest.mark.parametrize("quantity,months", [("three weeks", 21 / 30.4375),
                                          ("eight months", 8), ("one year and two months", 14)])
def test_subject_state_and_age_unit_combinations(subject, state, quantity, months):
    assert message_age_months(f"{subject} {state} {quantity}. Suggest a calm activity.") == pytest.approx(months)
