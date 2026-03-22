"""
Gaming-specific job board implementations.
Each class is a thin config wrapper around GenericGamingBoard.
"""
from __future__ import annotations

from src.job_boards.generic_gaming import GenericGamingBoard


class Hitmarker(GenericGamingBoard):
    BASE_URL = "https://hitmarker.net"
    SEARCH_URL = "https://hitmarker.net/jobs?q={query}"
    BOARD_NAME = "hitmarker"
    CARD_SELECTOR = ".job-listing-item, [class*='job-listing'], [class*='job-card'], article.job"
    TITLE_SELECTOR = ".job-listing-item__title, .job-title, h2 a, h3 a"
    COMPANY_SELECTOR = ".job-listing-item__company, .company, [class*='company']"
    LINK_SELECTOR = "a[href*='/jobs/']"
    DESCRIPTION_SELECTOR = ".job-description, [class*='description'], .content"
    APPLY_BTN_SELECTOR = 'a:has-text("Apply Now"), a:has-text("Apply"), a[href*="apply"]'


class GamesIndustry(GenericGamingBoard):
    BASE_URL = "https://www.gamesindustry.biz"
    SEARCH_URL = "https://www.gamesindustry.biz/jobs?q={query}"
    BOARD_NAME = "gamesindustry"
    CARD_SELECTOR = ".vacancy, .job-listing, article[class*='job'], li[class*='job']"
    TITLE_SELECTOR = "h2 a, h3 a, .vacancy-title a, .job-title a"
    COMPANY_SELECTOR = ".vacancy-company, .company, .employer, [class*='company']"
    LINK_SELECTOR = "a[href*='/jobs/']"
    DESCRIPTION_SELECTOR = ".vacancy-description, .job-description, .body-text"
    APPLY_BTN_SELECTOR = 'a:has-text("Apply Now"), a:has-text("Apply"), a[href*="apply"]'


class GrackleHQ(GenericGamingBoard):
    BASE_URL = "https://www.gracklehq.com"
    SEARCH_URL = "https://www.gracklehq.com/jobs?search={query}"
    BOARD_NAME = "gracklehq"
    CARD_SELECTOR = ".job, .listing, article, [class*='job-card'], [class*='job-item']"
    TITLE_SELECTOR = "h2 a, h3 a, .title a, [class*='job-title'] a"
    COMPANY_SELECTOR = ".company, .studio, [class*='company'], [class*='studio']"
    LINK_SELECTOR = "a[href*='/job']"
    DESCRIPTION_SELECTOR = ".description, [class*='description'], .content"
    APPLY_BTN_SELECTOR = 'a:has-text("Apply Now"), a:has-text("Apply"), button:has-text("Apply")'


class WorkWithIndies(GenericGamingBoard):
    BASE_URL = "https://www.workwithindies.com"
    SEARCH_URL = "https://www.workwithindies.com/jobs?q={query}"
    BOARD_NAME = "workwithindies"
    CARD_SELECTOR = ".job, article, .listing, [class*='job'], .card"
    TITLE_SELECTOR = "h2 a, h3 a, .job-title, [class*='title'] a"
    COMPANY_SELECTOR = ".studio, .company, [class*='company'], [class*='studio']"
    LINK_SELECTOR = "a[href*='/job']"
    DESCRIPTION_SELECTOR = ".description, [class*='description'], .body"
    APPLY_BTN_SELECTOR = 'a:has-text("Apply Now"), a:has-text("Apply"), a[href*="apply"]'


class RemoteGameJobs(GenericGamingBoard):
    BASE_URL = "https://remotegamejobs.com"
    SEARCH_URL = "https://remotegamejobs.com/?s={query}"
    BOARD_NAME = "remotegamejobs"
    CARD_SELECTOR = "article, .job, .listing, [class*='job'], .type-job_listing"
    TITLE_SELECTOR = "h2 a, h3 a, .entry-title a, [class*='title'] a"
    COMPANY_SELECTOR = ".company, .author, .job_listing-company, [class*='company']"
    LINK_SELECTOR = "a[href*='/job']"
    DESCRIPTION_SELECTOR = ".entry-content, .job_listing-description, .description"
    APPLY_BTN_SELECTOR = 'a:has-text("Apply Now"), a:has-text("Apply"), a[href*="apply"]'


class GamesCareer(GenericGamingBoard):
    BASE_URL = "https://www.games-career.com"
    SEARCH_URL = "https://www.games-career.com/en/jobs?keywords={query}"
    BOARD_NAME = "gamescareer"
    CARD_SELECTOR = ".job-item, .vacancy, article[class*='job'], .job-box"
    TITLE_SELECTOR = "h2 a, h3 a, .job-title a, .position-title a"
    COMPANY_SELECTOR = ".company, .employer, .company-name"
    LINK_SELECTOR = "a[href*='/en/jobs/']"
    DESCRIPTION_SELECTOR = ".job-description, .description, .vacancy-text"
    APPLY_BTN_SELECTOR = 'a:has-text("Apply Now"), a:has-text("Apply"), a[href*="apply"]'


class GamesJobsDirect(GenericGamingBoard):
    BASE_URL = "https://www.gamesjobsdirect.com"
    SEARCH_URL = "https://www.gamesjobsdirect.com/results?q={query}"
    BOARD_NAME = "gamesjobsdirect"
    CARD_SELECTOR = ".job-result, .vacancy, [class*='job-item'], .result-item"
    TITLE_SELECTOR = "h2 a, h3 a, .job-title a, .position a"
    COMPANY_SELECTOR = ".company-name, .employer, .company"
    LINK_SELECTOR = "a[href*='/details/']"
    DESCRIPTION_SELECTOR = ".job-description, .vacancy-description"
    APPLY_BTN_SELECTOR = 'a:has-text("Apply Now"), a:has-text("Apply"), a[href*="apply"]'


class GameJobsCo(GenericGamingBoard):
    BASE_URL = "https://gamejobs.co"
    SEARCH_URL = "https://gamejobs.co/search?q={query}"
    BOARD_NAME = "gamejobsco"
    CARD_SELECTOR = ".job-card, .listing, article, [class*='job'], .card"
    TITLE_SELECTOR = "h2 a, h3 a, .title a, [class*='title'] a"
    COMPANY_SELECTOR = ".company, .studio, [class*='company']"
    LINK_SELECTOR = "a[href*='/jobs/']"
    DESCRIPTION_SELECTOR = ".description, [class*='description'], .content"
    APPLY_BTN_SELECTOR = 'a:has-text("Apply Now"), a:has-text("Apply"), a[href*="apply"]'


class EightBit(GenericGamingBoard):
    BASE_URL = "https://www.8bitrecruiting.com"
    SEARCH_URL = "https://www.8bitrecruiting.com/jobs?q={query}"
    BOARD_NAME = "8bit"
    CARD_SELECTOR = ".job, .listing, article, [class*='job-card'], .vacancy"
    TITLE_SELECTOR = "h2 a, h3 a, .job-title, [class*='title'] a"
    COMPANY_SELECTOR = ".company, .client, [class*='company']"
    LINK_SELECTOR = "a[href*='/job']"
    DESCRIPTION_SELECTOR = ".description, [class*='description'], .job-details"
    APPLY_BTN_SELECTOR = 'a:has-text("Apply Now"), a:has-text("Apply"), a[href*="apply"]'


class InGameJob(GenericGamingBoard):
    BASE_URL = "https://ingamejob.com"
    SEARCH_URL = "https://ingamejob.com/en/job-offers?q={query}"
    BOARD_NAME = "ingamejob"
    CARD_SELECTOR = ".job-offer, .job, article, [class*='job'], .offer-item"
    TITLE_SELECTOR = "h2 a, h3 a, .offer-title a, [class*='title'] a"
    COMPANY_SELECTOR = ".company, .studio, .employer, [class*='company']"
    LINK_SELECTOR = "a[href*='/en/job']"
    DESCRIPTION_SELECTOR = ".job-description, .description, .offer-description"
    APPLY_BTN_SELECTOR = 'a:has-text("Apply Now"), a:has-text("Apply"), a[href*="apply"]'
