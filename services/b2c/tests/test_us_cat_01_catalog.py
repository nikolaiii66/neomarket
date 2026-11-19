"""US-CAT-01: catalog with filters, sort, facets; B2B proxy unhappy paths."""

import pytest

from app.schemas import ALLOWED_SORTS


def test_catalog_returns_filtered_sorted_products(client, seeded_catalog):
    """Category filter + price_asc sort + pagination."""
    response = client.get(
        "/api/v1/products",
        params={
            "category_id": seeded_catalog["category"].id,
            "sort": "price_asc",
            "limit": 1,
            "offset": 0,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 2
    assert body["limit"] == 1
    assert body["offset"] == 0
    assert len(body["items"]) == 1
    # Product 1 is cheaper (15000) than Product 2 (20000)
    assert body["items"][0]["id"] == seeded_catalog["products"][0].id

    page2 = client.get(
        "/api/v1/catalog/products",
        params={
            "category_id": seeded_catalog["category"].id,
            "sort": "price_asc",
            "limit": 1,
            "offset": 1,
        },
    )
    assert page2.status_code == 200
    assert page2.json()["items"][0]["id"] == seeded_catalog["products"][1].id


def test_facets_return_counts_per_filter_value(client, seeded_catalog):
    response = client.get(
        "/api/v1/catalog/facets",
        params={"category_id": seeded_catalog["category"].id},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["category_id"] == seeded_catalog["category"].id
    expected_filter_ids = {seeded_catalog["filters"][0].id}
    actual_filter_ids = {f["id"] for f in body["filters"]}
    assert expected_filter_ids == actual_filter_ids
    values = [val for facet in body["facets"] for val in facet.get("values", [])]
    values_by_value = {val["value"]: val["count"] for val in values}
    assert values_by_value["Apple"] == 1
    assert values_by_value["Samsung"] == 1


@pytest.mark.parametrize("sort", ["invalid", "title_asc", "title_desc", "totally_invalid"])
def test_invalid_sort_returns_400(client, seeded_catalog, sort):
    response = client.get(
        "/api/v1/products",
        params={"category_id": seeded_catalog["category"].id, "sort": sort},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "INVALID_REQUEST"
    msg = body["message"]
    for allowed in ("price_asc", "price_desc", "popularity", "new"):
        assert allowed in msg
    for allowed in ALLOWED_SORTS:
        assert allowed in msg


def test_b2b_unavailable_returns_502(client, seeded_catalog, b2b_client):
    b2b_client.unavailable = True
    response = client.get(
        "/api/v1/catalog/products",
        params={"category_id": seeded_catalog["category"].id, "sort": "popularity"},
    )
    assert response.status_code in (502, 503)
    assert response.json()["code"] == "B2B_UNAVAILABLE"

    facets = client.get(
        "/api/v1/catalog/facets",
        params={"category_id": seeded_catalog["category"].id},
    )
    assert facets.status_code in (502, 503)
    assert facets.json()["code"] == "B2B_UNAVAILABLE"


def test_search_title_returns_matching_products(client, seeded_catalog):
    response = client.get(
        "/api/v1/products",
        params={"category_id": seeded_catalog["category"].id, "search": "Product 1"},
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == seeded_catalog["products"][0].id


def test_search_description_returns_matching_products(client, seeded_catalog):
    response = client.get(
        "/api/v1/products",
        params={"category_id": seeded_catalog["category"].id, "search": "Description 1"},
    )
    assert response.status_code == 200
    assert len(response.json()["items"]) == 2


@pytest.mark.parametrize("search", ["t", "te", "tes"])
def test_short_query_returns_400(client, seeded_catalog, search):
    response = client.get(
        "/api/v1/products",
        params={"category_id": seeded_catalog["category"].id, "search": search},
    )
    assert response.status_code == 400


def test_empty_results_returns_200(client, seeded_catalog):
    response = client.get(
        "/api/v1/products",
        params={"category_id": seeded_catalog["category"].id, "search": "Not exists"},
    )
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_special_chars_do_not_break_query(client, seeded_catalog):
    response = client.get(
        "/api/v1/products",
        params={"category_id": seeded_catalog["category"].id, "search": "!@#$%^&*()"},
    )
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_products_list_filters_only_visible_products(client, visibility_catalog):
    response = client.get(
        "/api/v1/products",
        params={"category_id": visibility_catalog["category"].id},
    )
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["items"]}
    assert visibility_catalog["visible_product"].id in ids
    assert visibility_catalog["hidden_by_status_product"].id not in ids
    assert visibility_catalog["hidden_by_stock_product"].id not in ids


def test_facets_returns_empty_list_for_empty_category(client, db_session):
    from app.models import Category
    import uuid

    empty = Category(id=str(uuid.uuid4()), name="Empty", slug="empty")
    db_session.add(empty)
    db_session.commit()
    response = client.get("/api/v1/catalog/facets", params={"category_id": empty.id})
    assert response.status_code == 200
    body = response.json()
    assert body["category_id"] == empty.id
    assert body["facets"] == []


def test_price_filter_applies(client, seeded_catalog):
    response = client.get(
        "/api/v1/products",
        params={
            "category_id": seeded_catalog["category"].id,
            "price_max": 16000,
            "sort": "price_asc",
        },
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == seeded_catalog["products"][0].id
