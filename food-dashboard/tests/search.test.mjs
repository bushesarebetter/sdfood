import { test } from "node:test";
import assert from "node:assert/strict";
import { tokenize, searchPlaces, noMatchText } from "../src/lib/search.js";

const site = (name, address) => ({ properties: { name, address } });
const features = [
  site("Sample Taqueria 004", "1200 Example Ave, San Diego, CA 92109"),
  site("Sample Kitchen 011", "4400 Sample Row, San Diego, CA 92111"),
  site("Sample Noodle House 020", "4600 Sample Row, San Diego, CA 92111"),
  site("Sample Market 031", "3100 Example Ave, San Diego, CA 92109"),
];
const names = (q) => searchPlaces(features, q).map((f) => f.properties.name);

test("words match the name or the street, in any order, with abbreviations expanded", () => {
  assert.deepEqual(tokenize("example ave."), ["example", "avenue"]);
  assert.deepEqual(names("example avenue"), ["Sample Market 031", "Sample Taqueria 004"], "both on the same street, by name");
  assert.deepEqual(names("row noodle"), ["Sample Noodle House 020"]);
  assert.deepEqual(names("kitchen on sample row"), ["Sample Kitchen 011"]);
});

test("ties break on the name, missing words exclude, and no match says what the site lists", () => {
  assert.deepEqual(names("row"), ["Sample Kitchen 011", "Sample Noodle House 020"]);
  assert.deepEqual(names("row example"), []);
  assert.deepEqual(searchPlaces(features, "  "), []);
  assert.deepEqual(searchPlaces(null, "x"), []);
  assert.equal(
    noMatchText("taco hut ", { count: 5135, kinds: "restaurants and markets" }),
    "No listed place matches 'taco hut'. This site lists 5,135 City of San Diego restaurants and markets; a place that is not listed is not rated safe or unsafe.",
  );
});
